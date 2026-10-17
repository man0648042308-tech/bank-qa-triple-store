"""把四个可选参数转换为 Elasticsearch DSL 查询字典。"""

from __future__ import annotations

from typing import Any


def build_product_search_body(
    *,
    keyword: str | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    category: str | None = None,
) -> dict[str, Any]:
    """构造满足示例五合同的 ``bool.must + bool.filter`` 查询。

    ``keyword`` 影响相关度，所以放入 ``must``；价格和品类只是准入条件，不需要
    参与评分，所以放入 ``filter``。判断价格时使用 ``is not None``，这样合法的0元
    不会被Python当成假值而忽略。
    """

    if min_price is not None and max_price is not None and min_price > max_price:
        raise ValueError("min_price 不能大于 max_price")
    if min_price is not None and min_price < 0:
        raise ValueError("min_price 不能小于 0")
    if max_price is not None and max_price < 0:
        raise ValueError("max_price 不能小于 0")
    if keyword is not None and len(keyword) > 100:
        raise ValueError("keyword 不能超过 100 个字符")
    if category is not None and len(category) > 100:
        raise ValueError("category 不能超过 100 个字符")

    must: list[dict[str, Any]] = []
    filters: list[dict[str, Any]] = []

    cleaned_keyword = keyword.strip() if keyword is not None else ""
    if cleaned_keyword:
        must.append({"match": {"name": {"query": cleaned_keyword}}})
    else:
        # 没有关键词时仍返回可被价格/品类筛选的全部文档。
        must.append({"match_all": {}})

    price_range: dict[str, float] = {}
    if min_price is not None:
        price_range["gte"] = min_price
    if max_price is not None:
        price_range["lte"] = max_price
    if price_range:
        filters.append({"range": {"price": price_range}})

    cleaned_category = category.strip() if category is not None else ""
    if cleaned_category:
        filters.append({"term": {"category": cleaned_category}})

    return {
        "query": {"bool": {"must": must, "filter": filters}},
        "size": 10,
        "sort": [{"_score": {"order": "desc"}}],
        "highlight": {
            "pre_tags": ["<em>"],
            "post_tags": ["</em>"],
            "fields": {"name": {}},
        },
    }
