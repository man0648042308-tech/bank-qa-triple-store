"""执行示例五查询，并把ES原始字典转换成容易理解的结构化结果。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .query_builder import build_product_search_body


@dataclass(frozen=True, slots=True)
class ProductSearchHit:
    """一条产品搜索命中。"""

    product_id: int
    name: str
    highlighted_name: str
    category: str
    price: float
    stock: int
    score: float


@dataclass(frozen=True, slots=True)
class ProductSearchResponse:
    """搜索总命中数和当前页（最多10条）结果。"""

    total: int
    items: tuple[ProductSearchHit, ...]


class ElasticsearchProductSearch:
    """真实ES客户端适配器；客户端通过构造参数注入，便于测试。"""

    def __init__(self, client: object, index_name: str) -> None:
        self._client = client
        self._index_name = index_name

    def search_products(
        self,
        *,
        keyword: str | None = None,
        min_price: float | None = None,
        max_price: float | None = None,
        category: str | None = None,
    ) -> ProductSearchResponse:
        body = build_product_search_body(
            keyword=keyword,
            min_price=min_price,
            max_price=max_price,
            category=category,
        )
        raw = self._client.search(  # type: ignore[attr-defined]
            index=self._index_name,
            **body,
        )
        raw_hits = raw.get("hits", {})
        total_value = raw_hits.get("total", 0)
        # ES 7/8通常返回 {"value": 3, "relation": "eq"}，假客户端也可能直接返回整数。
        total = (
            int(total_value.get("value", 0))
            if isinstance(total_value, dict)
            else int(total_value)
        )

        items: list[ProductSearchHit] = []
        for hit in raw_hits.get("hits", []):
            source: dict[str, Any] = hit.get("_source", {})
            highlighted_values = hit.get("highlight", {}).get("name", [])
            highlighted_name = (
                str(highlighted_values[0]) if highlighted_values else str(source.get("name", ""))
            )
            items.append(
                ProductSearchHit(
                    product_id=int(source.get("product_id") or hit.get("_id", 0)),
                    name=str(source.get("name", "")),
                    highlighted_name=highlighted_name,
                    category=str(source.get("category", "")),
                    price=float(source.get("price", 0.0)),
                    stock=int(source.get("stock", 0)),
                    score=float(hit.get("_score") or 0.0),
                )
            )
        return ProductSearchResponse(total=total, items=tuple(items))


def search_products(
    client: object,
    index_name: str,
    *,
    keyword: str | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    category: str | None = None,
) -> ProductSearchResponse:
    """函数式入口：内部仍复用适配器，方便演示直接调用。"""

    return ElasticsearchProductSearch(client, index_name).search_products(
        keyword=keyword,
        min_price=min_price,
        max_price=max_price,
        category=category,
    )
