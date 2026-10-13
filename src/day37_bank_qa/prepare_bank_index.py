"""创建银行问答专用ES索引并写入五个固定产品。

只操作 ``day37_bank_knowledge_v1``。脚本不会删除索引；遇到未知映射或文档ID时
直接拒绝，重复运行只会用相同产品ID更新本作业五条文档。中文教学数据使用
1～2字的ngram分析器，避免依赖必须与服务器完全同版的IK插件。
"""

from __future__ import annotations

from elasticsearch import Elasticsearch

from .sample_data import PRODUCTS
from .settings import Settings

BANK_INDEX_SETTINGS = {
    "analysis": {
        "analyzer": {
            "day37_cn_ngram": {
                "type": "custom",
                "tokenizer": "day37_ngram_tokenizer",
                "filter": ["lowercase"],
            }
        },
        "tokenizer": {
            "day37_ngram_tokenizer": {
                "type": "ngram",
                "min_gram": 1,
                "max_gram": 2,
                "token_chars": ["letter", "digit"],
            }
        },
    }
}

BANK_INDEX_MAPPINGS = {
    "properties": {
        "dataset_id": {"type": "keyword"},
        "product_id": {"type": "keyword"},
        "name": {
            "type": "text",
            "analyzer": "day37_cn_ngram",
            "search_analyzer": "standard",
        },
        "category": {"type": "keyword"},
        "risk_level": {"type": "keyword"},
        "min_investment": {"type": "integer"},
        "status": {"type": "keyword"},
        "description": {
            "type": "text",
            "analyzer": "day37_cn_ngram",
            "search_analyzer": "standard",
        },
        "content": {
            "type": "text",
            "analyzer": "day37_cn_ngram",
            "search_analyzer": "standard",
        },
    }
}


def _bank_documents() -> dict[str, dict[str, object]]:
    """把固定产品转换为索引文档，并以产品ID建立验收字典。"""

    return {
        product.product_id: {
            "dataset_id": "day37",
            "product_id": product.product_id,
            "name": product.name,
            "category": product.category,
            "risk_level": product.risk_level,
            "min_investment": product.min_investment,
            "status": product.status,
            "description": product.description,
            "content": (
                f"{product.name}属于{product.category}，风险等级{product.risk_level}，"
                f"起投金额{product.min_investment}元。{product.description}"
            ),
        }
        for product in PRODUCTS
    }


def _assert_bank_mapping(client: Elasticsearch, index_name: str) -> None:
    """检查字段集合、类型和分析器；不符合时保护性失败。"""

    raw = client.indices.get_mapping(index=index_name)
    actual = dict(next(iter(raw.values())).get("mappings", {}).get("properties", {}))
    expected = BANK_INDEX_MAPPINGS["properties"]
    if set(actual) != set(expected):
        raise RuntimeError(
            f"索引 {index_name} 字段集合不符合银行知识合同；程序不会删除未知索引。"
        )
    for field_name, expected_config in expected.items():
        for key, expected_value in expected_config.items():
            if actual[field_name].get(key) != expected_value:
                raise RuntimeError(
                    f"索引 {index_name} 字段 {field_name}.{key} 不符合合同；"
                    "程序不会删除未知索引。"
                )


def _read_bank_documents(
    client: Elasticsearch,
    index_name: str,
) -> tuple[int, dict[str, dict[str, object]]]:
    response = client.search(
        index=index_name,
        size=6,
        query={"match_all": {}},
        sort=[{"product_id": {"order": "asc"}}],
    )
    raw_total = response.get("hits", {}).get("total", 0)
    total = (
        int(raw_total.get("value", 0))
        if isinstance(raw_total, dict)
        else int(raw_total)
    )
    documents: dict[str, dict[str, object]] = {}
    for hit in response.get("hits", {}).get("hits", []):
        document_id = str(hit.get("_id", ""))
        source = dict(hit.get("_source", {}))
        if str(source.get("product_id", "")) != document_id:
            raise RuntimeError(
                f"索引 {index_name} 的文档_id={document_id}与product_id不一致；拒绝继续。"
            )
        documents[document_id] = source
    return total, documents


def _assert_bank_ownership(
    client: Elasticsearch,
    index_name: str,
    *,
    require_complete: bool,
) -> None:
    expected = _bank_documents()
    total, actual = _read_bank_documents(client, index_name)
    if total != len(actual):
        raise RuntimeError(
            f"索引 {index_name} 实际文档数为{total}，超出可验证的本作业文档；拒绝继续。"
        )
    unexpected_ids = sorted(set(actual) - set(expected))
    if unexpected_ids:
        raise RuntimeError(
            f"索引 {index_name} 含未知文档ID {unexpected_ids}；程序拒绝覆盖或删除。"
        )
    # 相同产品ID仍可能保存其他内容；类型与值都吻合才允许继续幂等初始化。
    for document_id, document in actual.items():
        expected_document = expected[document_id]
        if set(document) != set(expected_document) or any(
            type(document[field]) is not type(expected_document[field])
            or document[field] != expected_document[field]
            for field in expected_document
        ):
            raise RuntimeError(
                f"索引 {index_name} 的文档{document_id}字段、值或类型不符合固定合同；拒绝覆盖。"
            )
    if require_complete and actual != expected:
        raise RuntimeError(f"索引 {index_name} 写入后未满足5条银行知识合同")


def prepare_bank_index(client: Elasticsearch, index_name: str) -> int:
    """创建或验证专用索引，写入五条银行知识，再执行强校验。"""

    if not client.indices.exists(index=index_name):
        client.indices.create(
            index=index_name,
            settings=BANK_INDEX_SETTINGS,
            mappings=BANK_INDEX_MAPPINGS,
        )
    _assert_bank_mapping(client, index_name)
    _assert_bank_ownership(client, index_name, require_complete=False)
    for product_id, document in _bank_documents().items():
        client.index(index=index_name, id=product_id, document=document)
    client.indices.refresh(index=index_name)
    _assert_bank_ownership(client, index_name, require_complete=True)
    return len(PRODUCTS)


def main() -> None:
    settings = Settings.from_env()
    client = Elasticsearch(settings.es_url, request_timeout=10)
    count = prepare_bank_index(client, settings.es_index)
    print(f"银行知识索引准备完成：{settings.es_index}，固定数据 {count} 条")


if __name__ == "__main__":
    main()



