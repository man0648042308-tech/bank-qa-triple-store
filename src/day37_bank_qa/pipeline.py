"""银行问答主流水线：画像 → 意图 → 缓存 → 检索 → 融合 → 规则 → 回答。"""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace

from langchain_core.runnables import RunnableLambda

from .answer_generator import AnswerGenerator, DeterministicAnswerGenerator
from .business_rules import check_product_eligibility
from .cache import InMemoryTTLCache, TextCache, build_cache_key
from .elasticsearch_retriever import FixtureTextRetriever, Retriever
from .models import Answer, Customer, Product, RetrievalHit
from .neo4j_repository import (
    CustomerRepository,
    FixtureCustomerRepository,
    FixtureGraphRetriever,
    GraphRetriever,
)
from .query_intent import QueryIntent, classify_query, select_fact_product_ids
from .rrf import reciprocal_rank_fusion
from .sample_data import PRODUCTS


class CustomerNotFoundError(LookupError):
    """客户编号不存在时抛出的业务异常。"""


def _profile_fingerprint(customer: Customer) -> str:
    """把影响资格判断的客户字段变成稳定文本。"""

    return f"{customer.name}|{customer.risk_level.upper()}|{customer.available_amount}"


def _catalog_fingerprint(products: dict[str, Product]) -> str:
    """产品风险、金额或状态变化时得到不同摘要。"""

    rows = [
        "|".join(
            (
                product.product_id,
                product.name,
                product.category,
                product.risk_level,
                str(product.min_investment),
                product.status,
                product.description,
            )
        )
        for product in sorted(products.values(), key=lambda item: item.product_id)
    ]
    return hashlib.sha256("\n".join(rows).encode("utf-8")).hexdigest()


def _product_from_hit(hit: RetrievalHit, products: dict[str, Product]) -> Product | None:
    """优先读取权威产品表；真实检索新产品时再从命中元数据构造产品。"""

    if hit.product_id is None:
        return None
    existing = products.get(hit.product_id)
    if existing is not None:
        return existing
    required = {"category", "risk_level", "min_investment", "status"}
    if not required.issubset(hit.metadata):
        return None
    return Product(
        product_id=hit.product_id,
        name=hit.title,
        category=str(hit.metadata["category"]),
        risk_level=str(hit.metadata["risk_level"]),
        min_investment=int(hit.metadata["min_investment"]),
        status=str(hit.metadata["status"]),
        description=hit.content,
    )


class BankQAPipeline:
    """组合多个小模块，并保证大模型之前一定执行硬业务规则。"""

    def __init__(
        self,
        *,
        customer_repository: CustomerRepository,
        text_retriever: Retriever,
        graph_retriever: GraphRetriever,
        products: tuple[Product, ...] = PRODUCTS,
        answer_generator: AnswerGenerator | None = None,
        cache: TextCache | None = None,
        cache_ttl_seconds: int = 300,
        data_version: str = "v1",
    ) -> None:
        self._customer_repository = customer_repository
        self._text_retriever = text_retriever
        self._graph_retriever = graph_retriever
        self._products = {product.product_id: product for product in products}
        self._answer_generator = answer_generator or DeterministicAnswerGenerator()
        self._cache = cache
        self._cache_ttl_seconds = cache_ttl_seconds
        self._data_version = data_version

    def ask(self, customer_id: str, question: str, *, top_k: int = 5) -> Answer:
        """执行一次完整问答，并返回结构化 ``Answer``。"""

        if not question.strip():
            raise ValueError("question 不能为空")
        if len(question) > 500:
            raise ValueError("question 不能超过 500 个字符")
        if not customer_id.strip() or len(customer_id) > 32:
            raise ValueError("customer_id 长度必须是 1～32 个字符")
        if top_k <= 0:
            raise ValueError("top_k 必须大于 0")

        customer = self._customer_repository.get_customer(customer_id)
        if customer is None:
            raise CustomerNotFoundError(f"找不到客户：{customer_id}")

        products = tuple(self._products.values())
        intent = classify_query(question, products)
        if intent is QueryIntent.OUT_OF_SCOPE:
            return self._answer_generator.generate(question, customer, [], intent=intent)

        cache_key = build_cache_key(
            customer.customer_id,
            question,
            self._data_version,
            profile_fingerprint=_profile_fingerprint(customer),
            catalog_fingerprint=_catalog_fingerprint(self._products),
        )
        if self._cache is not None:
            cached_json = self._cache.get(cache_key)
            if cached_json is not None:
                try:
                    cached_answer = Answer.from_dict(json.loads(cached_json))
                except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                    cached_answer = None
                if cached_answer is not None and self._cached_answer_is_safe(
                    cached_answer, customer, intent
                ):
                    return replace(cached_answer, cache_hit=True)

        es_hits = self._text_retriever.search(question, top_k=top_k * 2)
        graph_hits = self._graph_retriever.search(customer.customer_id, question, top_k=top_k * 2)
        fused_hits = reciprocal_rank_fusion(
            {"elasticsearch": es_hits, "neo4j": graph_hits},
            top_k=top_k * 2,
        )

        selected_hits: list[RetrievalHit] = []
        if intent is QueryIntent.PRODUCT_FACT:
            target_ids = select_fact_product_ids(question, products)
            selected_hits = [
                hit
                for hit in fused_hits
                if hit.product_id is not None
                and (not target_ids or hit.product_id in target_ids)
            ][:top_k]
        else:
            for hit in fused_hits:
                product = _product_from_hit(hit, self._products)
                if product is None:
                    continue
                if check_product_eligibility(customer, product).allowed:
                    selected_hits.append(hit)
                if len(selected_hits) >= top_k:
                    break

        answer = self._answer_generator.generate(
            question,
            customer,
            selected_hits,
            intent=intent,
        )
        if self._cache is not None:
            self._cache.set(
                cache_key,
                json.dumps(answer.to_dict(), ensure_ascii=False),
                self._cache_ttl_seconds,
            )
        return answer

    def _cached_answer_is_safe(
        self,
        answer: Answer,
        customer: Customer,
        intent: QueryIntent,
    ) -> bool:
        """即使缓存键合同被误改，也不返回当前已不合规的推荐。"""

        if intent is not QueryIntent.RECOMMENDATION:
            return not answer.recommended_product_ids
        for product_id in answer.recommended_product_ids:
            product = self._products.get(product_id)
            if product is None or not check_product_eligibility(customer, product).allowed:
                return False
        return True

    def as_runnable(self) -> RunnableLambda:
        """把普通Python方法包装成LangChain 1.x的可调用组件。"""

        return RunnableLambda(
            lambda payload: self.ask(
                customer_id=str(payload["customer_id"]),
                question=str(payload["question"]),
                top_k=int(payload.get("top_k", 5)),
            )
        )


def build_offline_pipeline() -> BankQAPipeline:
    """构建不连接ES/Redis/Neo4j也可以运行的完整教学流水线。"""

    return BankQAPipeline(
        customer_repository=FixtureCustomerRepository(),
        text_retriever=FixtureTextRetriever(),
        graph_retriever=FixtureGraphRetriever(),
        cache=InMemoryTTLCache(),
    )
