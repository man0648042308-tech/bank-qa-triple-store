from __future__ import annotations

import pytest

from exercise05.prepare_product_index import EXERCISE_PRODUCTS, INDEX_MAPPINGS
from exercise05.query_builder import build_product_search_body
from exercise05.search_products import ElasticsearchProductSearch


def test_all_four_optional_conditions_are_put_in_correct_bool_sections() -> None:
    body = build_product_search_body(
        keyword="phone",
        min_price=100,
        max_price=800,
        category="electronics",
    )

    bool_query = body["query"]["bool"]
    assert bool_query["must"] == [{"match": {"name": {"query": "phone"}}}]
    assert {"range": {"price": {"gte": 100, "lte": 800}}} in bool_query["filter"]
    assert {"term": {"category": "electronics"}} in bool_query["filter"]
    assert body["size"] == 10
    assert body["sort"] == [{"_score": {"order": "desc"}}]
    assert body["highlight"]["pre_tags"] == ["<em>"]
    assert body["highlight"]["post_tags"] == ["</em>"]
    assert "name" in body["highlight"]["fields"]


def test_all_parameters_are_optional_and_zero_price_is_not_lost() -> None:
    no_condition = build_product_search_body()
    zero_price = build_product_search_body(min_price=0, max_price=0)

    assert no_condition["query"]["bool"]["must"] == [{"match_all": {}}]
    assert no_condition["query"]["bool"]["filter"] == []
    assert zero_price["query"]["bool"]["filter"] == [
        {"range": {"price": {"gte": 0, "lte": 0}}}
    ]


@pytest.mark.parametrize(
    ("min_price", "max_price"),
    [(-1, None), (None, -1), (900, 100)],
)
def test_invalid_price_range_is_rejected(
    min_price: float | None,
    max_price: float | None,
) -> None:
    with pytest.raises(ValueError):
        build_product_search_body(min_price=min_price, max_price=max_price)


def test_decimal_price_boundaries_and_input_length_are_supported() -> None:
    body = build_product_search_body(min_price=100.5, max_price=800.75)

    assert body["query"]["bool"]["filter"] == [
        {"range": {"price": {"gte": 100.5, "lte": 800.75}}}
    ]
    with pytest.raises(ValueError, match="keyword"):
        build_product_search_body(keyword="x" * 101)


def test_exercise_two_contract_has_100_deterministic_full_documents() -> None:
    assert len(EXERCISE_PRODUCTS) == 100
    assert EXERCISE_PRODUCTS[0] == {
        "product_id": 1,
        "name": "phone model 001",
        "category": "electronics",
        "price": 75.5,
        "stock": 7,
        "release_date": "2026-01-01",
    }
    assert set(EXERCISE_PRODUCTS[0]) == {
        "product_id",
        "name",
        "category",
        "price",
        "stock",
        "release_date",
    }
    mappings = INDEX_MAPPINGS["properties"]
    assert mappings["product_id"]["type"] == "integer"
    assert mappings["price"]["type"] == "float"
    assert mappings["stock"]["type"] == "integer"
    assert mappings["release_date"]["type"] == "date"


class FakeElasticsearch:
    def __init__(self) -> None:
        self.kwargs: dict[str, object] = {}

    def search(self, **kwargs: object) -> dict[str, object]:
        self.kwargs = kwargs
        return {
            "hits": {
                "total": {"value": 2, "relation": "eq"},
                "hits": [
                    {
                        "_id": "1",
                        "_score": 3.5,
                        "_source": {
                            "product_id": 1,
                            "name": "phone model 001",
                            "category": "electronics",
                            "price": 75.5,
                            "stock": 7,
                        },
                        "highlight": {"name": ["<em>phone</em> model 001"]},
                    },
                    {
                        "_id": "17",
                        "_score": 2.0,
                        "_source": {
                            "product_id": 17,
                            "name": "phone model 017",
                            "category": "electronics",
                            "price": 483.5,
                            "stock": 18,
                        },
                    },
                ],
            }
        }


def test_real_adapter_preserves_total_highlight_stock_and_query_contract() -> None:
    client = FakeElasticsearch()
    response = ElasticsearchProductSearch(client, "day37_product_exercise_v1").search_products(
        keyword="phone", min_price=100, max_price=800
    )

    assert client.kwargs["index"] == "day37_product_exercise_v1"
    assert client.kwargs["size"] == 10
    assert client.kwargs["sort"] == [{"_score": {"order": "desc"}}]
    assert response.total == 2
    assert response.items[0].product_id == 1
    assert response.items[0].highlighted_name == "<em>phone</em> model 001"
    assert response.items[0].stock == 7
    assert response.items[1].highlighted_name == "phone model 017"
