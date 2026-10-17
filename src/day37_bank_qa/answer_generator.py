"""确定性回答器，以及带输出后置校验的可替换大模型回答器。"""

from __future__ import annotations

import re
from typing import Protocol

from .models import Answer, Customer, RetrievalHit
from .query_intent import QueryIntent


class AnswerGenerator(Protocol):
    """回答生成器必须实现的合同。"""

    def generate(
        self,
        question: str,
        customer: Customer,
        hits: list[RetrievalHit],
        *,
        intent: QueryIntent,
    ) -> Answer: ...


class InvokableModel(Protocol):
    """兼容LangChain聊天模型等具有 ``invoke`` 方法的对象。"""

    def invoke(self, input: str) -> object: ...


class DeterministicAnswerGenerator:
    """不用外部模型、每次输出相同的回答器，适合项目验收。"""

    def generate(
        self,
        question: str,
        customer: Customer,
        hits: list[RetrievalHit],
        *,
        intent: QueryIntent,
    ) -> Answer:
        if intent is QueryIntent.OUT_OF_SCOPE:
            return Answer(
                question=question,
                customer_id=customer.customer_id,
                text="该问题不属于银行产品问答范围，请改问产品特点、风险、起投金额或推荐。",
                sources=(),
                recommended_product_ids=(),
            )
        if not hits:
            return Answer(
                question=question,
                customer_id=customer.customer_id,
                text=(
                    "没有找到相关产品事实，请补充产品名称或编号。"
                    if intent is QueryIntent.PRODUCT_FACT
                    else "没有找到同时满足风险等级、可用金额和在售状态的产品，"
                    "请咨询客户经理。"
                ),
                sources=(),
                recommended_product_ids=(),
            )

        if intent is QueryIntent.PRODUCT_FACT:
            return self._generate_fact_answer(question, customer, hits)

        product_lines = [
            f"{index}. {hit.title}（产品编号：{hit.product_id}）"
            for index, hit in enumerate(hits, start=1)
        ]
        text = (
            f"客户{customer.name}的风险等级为{customer.risk_level}，"
            f"当前可用金额为{customer.available_amount}元。\n"
            "经过检索与硬规则过滤，可参考以下产品：\n"
            + "\n".join(product_lines)
            + "\n以上内容仅用于功能演示，不构成真实投资建议。"
        )
        return Answer(
            question=question,
            customer_id=customer.customer_id,
            text=text,
            sources=tuple(f"{hit.source}:{hit.source_id}" for hit in hits),
            recommended_product_ids=tuple(
                hit.product_id for hit in hits if hit.product_id is not None
            ),
        )

    @staticmethod
    def _generate_fact_answer(
        question: str,
        customer: Customer,
        hits: list[RetrievalHit],
    ) -> Answer:
        """只陈述命中证据中的产品事实，不把事实查询标记成个性化推荐。"""

        wants_risk = "风险" in question
        wants_amount = "起投" in question or "金额" in question
        wants_description = any(term in question for term in ("特点", "介绍", "怎么样"))
        lines: list[str] = []
        for hit in hits:
            facts: list[str] = []
            if wants_risk or not (wants_risk or wants_amount or wants_description):
                facts.append(f"风险等级{hit.metadata.get('risk_level', '未知')}")
            if wants_amount or not (wants_risk or wants_amount or wants_description):
                facts.append(f"起投金额{hit.metadata.get('min_investment', '未知')}元")
            if wants_description or not (wants_risk or wants_amount or wants_description):
                facts.append(hit.content or "暂无特点说明")
            lines.append(f"{hit.title}（{hit.product_id}）：" + "；".join(facts))
        return Answer(
            question=question,
            customer_id=customer.customer_id,
            text="根据产品资料：\n" + "\n".join(lines) + "\n以上为产品事实，不构成购买建议。",
            sources=tuple(f"{hit.source}:{hit.source_id}" for hit in hits),
            recommended_product_ids=(),
        )


class OptionalLLMAnswerGenerator:
    """把已通过硬规则的证据交给可插拔模型润色，不让模型绕过资格判断。"""

    def __init__(self, model: InvokableModel) -> None:
        self._model = model

    def generate(
        self,
        question: str,
        customer: Customer,
        hits: list[RetrievalHit],
        *,
        intent: QueryIntent,
    ) -> Answer:
        fallback = DeterministicAnswerGenerator()
        if intent is not QueryIntent.RECOMMENDATION or not hits:
            return fallback.generate(question, customer, hits, intent=intent)

        context = "\n".join(
            f"- [{hit.source}:{hit.source_id}] {hit.title}: {hit.content}" for hit in hits
        )
        prompt = (
            "你是银行功能演示助手。只能使用给定证据回答，不能新增产品或承诺收益。\n"
            f"客户风险等级：{customer.risk_level}\n"
            f"客户可用金额：{customer.available_amount}\n"
            f"问题：{question}\n"
            f"已通过确定性业务规则的证据：\n{context}\n"
            "请给出简短回答，并保留来源编号。"
        )
        raw = self._model.invoke(prompt)
        text = getattr(raw, "content", raw)
        candidate_text = str(text)
        allowed_ids = {hit.product_id for hit in hits if hit.product_id is not None}
        mentioned_ids = set(
            re.findall(
                r"(?<![A-Za-z0-9])P\d{3}(?![A-Za-z0-9])",
                candidate_text,
                flags=re.IGNORECASE,
            )
        )
        prohibited_claims = ("保证收益", "稳赚", "保本保收益", "绝对安全", "零风险")
        # 模型必须明确引用至少一个已过滤产品，且不能引入新ID或收益承诺；否则回退。
        if (
            not (mentioned_ids & allowed_ids)
            or not mentioned_ids.issubset(allowed_ids)
            or any(claim in candidate_text for claim in prohibited_claims)
        ):
            return fallback.generate(question, customer, hits, intent=intent)
        return Answer(
            question=question,
            customer_id=customer.customer_id,
            text=candidate_text,
            sources=tuple(f"{hit.source}:{hit.source_id}" for hit in hits),
            recommended_product_ids=tuple(
                hit.product_id for hit in hits if hit.product_id is not None
            ),
        )
