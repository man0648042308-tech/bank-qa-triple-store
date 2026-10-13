"""真实ES验收：只读查询既有Day37索引，不删除或重建任何资源。"""

from __future__ import annotations

from elasticsearch import Elasticsearch

from day37_bank_qa.prepare_bank_index import BANK_INDEX_MAPPINGS
from day37_bank_qa.settings import Settings
from exercise05.prepare_product_index import EXERCISE_PRODUCTS, INDEX_MAPPINGS
from exercise05.search_products import ElasticsearchProductSearch


def _total(response: dict[str, object]) -> int:
    hits = response.get("hits", {})
    raw_total = hits.get("total", 0) if isinstance(hits, dict) else 0
    return int(raw_total.get("value", 0)) if isinstance(raw_total, dict) else int(raw_total)


def _mapping_types(client: Elasticsearch, index_name: str) -> dict[str, object]:
    raw = client.indices.get_mapping(index=index_name)
    properties = next(iter(raw.values())).get("mappings", {}).get("properties", {})
    return {name: config.get("type") for name, config in properties.items()}


def main() -> None:
    settings = Settings.from_env()
    client = Elasticsearch(settings.es_url, request_timeout=10)
    if not client.ping():
        raise RuntimeError(f"Elasticsearch不可达：{settings.es_url}")
    if not client.indices.exists(index=settings.exercise_index):
        raise RuntimeError(f"练习索引不存在：{settings.exercise_index}，请先运行初始化脚本")
    if not client.indices.exists(index=settings.es_index):
        raise RuntimeError(f"银行知识索引不存在：{settings.es_index}，请先运行初始化脚本")

    expected_exercise_types = {
        name: config["type"] for name, config in INDEX_MAPPINGS["properties"].items()
    }
    expected_bank_types = {
        name: config["type"] for name, config in BANK_INDEX_MAPPINGS["properties"].items()
    }
    assert _mapping_types(client, settings.exercise_index) == expected_exercise_types
    assert _mapping_types(client, settings.es_index) == expected_bank_types

    exercise_raw = client.search(
        index=settings.exercise_index,
        size=100,
        query={"match_all": {}},
        sort=[{"product_id": {"order": "asc"}}],
    )
    exercise_hits = exercise_raw["hits"]["hits"]
    assert _total(exercise_raw) == 100, "练习索引必须恰好100条"
    assert len(exercise_hits) == 100
    expected_by_id = {int(item["product_id"]): item for item in EXERCISE_PRODUCTS}
    actual_by_id = {
        int(hit["_source"]["product_id"]): hit["_source"] for hit in exercise_hits
    }
    assert actual_by_id == expected_by_id, "练习索引字段、值或类型与固定合同不一致"
    assert all(
        type(source["product_id"]) is int
        and type(source["name"]) is str
        and type(source["category"]) is str
        and type(source["price"]) is float
        and type(source["stock"]) is int
        and type(source["release_date"]) is str
        for source in actual_by_id.values()
    ), "练习索引六个字段的Python反序列化类型不符合合同"

    analysis = client.indices.analyze(
        index=settings.exercise_index,
        field="name",
        text="phone model 001",
    )
    tokens = [item["token"] for item in analysis.get("tokens", [])]
    assert "phone" in tokens, f"name字段必须能把phone拆成独立词元，实际tokens={tokens}"

    bank_raw = client.search(
        index=settings.es_index,
        size=10,
        query={"term": {"dataset_id": "day37"}},
        sort=[{"product_id": {"order": "asc"}}],
    )
    bank_hits = bank_raw["hits"]["hits"]
    assert _total(bank_raw) == 5, "银行知识索引必须恰好有5条day37数据"
    assert [hit["_source"]["product_id"] for hit in bank_hits] == [
        "P001",
        "P002",
        "P003",
        "P004",
        "P005",
    ]
    expected_bank_fields = set(BANK_INDEX_MAPPINGS["properties"])
    assert all(set(hit["_source"]) == expected_bank_fields for hit in bank_hits)
    assert all(
        type(hit["_source"]["min_investment"]) is int
        and all(
            type(hit["_source"][field]) is str
            for field in expected_bank_fields - {"min_investment"}
        )
        for hit in bank_hits
    ), "银行知识字段类型不符合合同"

    search = ElasticsearchProductSearch(client, settings.exercise_index)
    phone = search.search_products(keyword="phone", min_price=100, max_price=800)
    electronics = search.search_products(category="electronics", min_price=500)

    assert phone.total == 1, "固定数据中keyword=phone,min=100,max=800应恰好命中1条"
    assert 0 < len(phone.items) <= 10
    assert all(100 <= item.price <= 800 for item in phone.items)
    assert all("<em>" in item.highlighted_name for item in phone.items)
    assert electronics.total == 20, "固定数据中electronics且价格>=500应恰好20条"
    assert 0 < len(electronics.items) <= 10
    assert all(item.category == "electronics" and item.price >= 500 for item in electronics.items)
    assert all(
        left.score >= right.score
        for left, right in zip(phone.items, phone.items[1:], strict=False)
    )
    print(
        "ELASTICSEARCH_VERIFY_PASS "
        f"exercise_count=100 bank_count=5 phone_total={phone.total} "
        f"electronics_total={electronics.total} analyze_phone=True"
    )


if __name__ == "__main__":
    main()

