"""银行知识的 Elasticsearch 检索器，以及无需数据库的固定数据检索器。"""

from __future__ import annotations

from typing import Protocol

from .models import RetrievalHit
from .sample_data import PRODUCTS, product_to_hit


class Retriever(Protocol):
    """文本检索器的最小合同。"""

    def search(self, query: str, *, top_k: int = 10) -> list[RetrievalHit]: ...


class ElasticsearchBankRetriever:
    """调用真实ES索引并把命中结果转换为统一的 ``RetrievalHit``。"""

    def __init__(self, client: object, index_name: str) -> None:
        self._client = client
        self._index_name = index_name

    def search(self, query: str, *, top_k: int = 10) -> list[RetrievalHit]:
        if not query.strip():
            return []
        response = self._client.search(  # type: ignore[attr-defined]
            index=self._index_name,
            size=top_k,
            query={
                "bool": {
                    "must": [
                        {
                            "multi_match": {
                                "query": query,
                                "fields": [
                                    "name^3",
                                    "description^2",
                                    "category",
                                    "content",
                                ],
                            }
                        }
                    ],
                    # 即使专属索引被误写入其他课程数据，也只召回dataset_id=day37。
                    "filter": [{"term": {"dataset_id": "day37"}}],
                }
            },
        )
        hits: list[RetrievalHit] = []
        for item in response.get("hits", {}).get("hits", []):
            source = item.get("_source", {})
            product_id = source.get("product_id")
            hits.append(
                RetrievalHit(
                    source_id=str(product_id or item.get("_id", "")),
                    title=str(source.get("name") or source.get("title") or "未命名资料"),
                    content=str(source.get("description") or source.get("content") or ""),
                    score=float(item.get("_score") or 0.0),
                    source="elasticsearch",
                    product_id=str(product_id) if product_id else None,
                    metadata={
                        key: source[key]
                        for key in ("category", "risk_level", "min_investment", "status")
                        if key in source
                    },
                )
            )
        return hits


class FixtureTextRetriever:
    """离线教学检索器：使用固定数据模拟“ES已经召回候选”的结果。"""

    def search(self, query: str, *, top_k: int = 10) -> list[RetrievalHit]:
        normalized = query.strip().casefold()
        ranked: list[RetrievalHit] = []
        for position, product in enumerate(PRODUCTS, start=1):
            searchable_text = f"{product.name} {product.category} {product.description}".casefold()
            keyword_bonus = sum(
                1 for token in normalized if token.strip() and token in searchable_text
            )
            # 即使问题只写“请推荐”，仍召回候选，再由硬规则决定哪些产品可以推荐。
            score = float(keyword_bonus * 10 + len(PRODUCTS) - position + 1)
            ranked.append(product_to_hit(product, source="elasticsearch", score=score))
        ranked.sort(key=lambda hit: (-hit.score, hit.source_id))
        return ranked[:top_k]


