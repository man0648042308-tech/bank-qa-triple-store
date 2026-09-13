"""创建练习五专用索引并写入固定演示数据。

脚本不会删除任何索引。若同名索引的映射或文档ID不属于本作业，脚本会拒绝继续，
避免通过覆盖或删除未知资源来制造“验收通过”。
"""

from __future__ import annotations

from elasticsearch import Elasticsearch

from day37_bank_qa.settings import Settings

CATEGORIES = ("electronics", "books", "home", "sports")
ELECTRONICS_NAMES = ("phone", "laptop", "tablet", "headphones")


def build_exercise_products(count: int = 100) -> tuple[dict[str, object], ...]:
    """按照练习二字段合同生成固定数据；同样输入永远得到同样结果。"""

    products: list[dict[str, object]] = []
    for product_id in range(1, count + 1):
        category = CATEGORIES[(product_id - 1) % len(CATEGORIES)]
        if category == "electronics":
            group_index = (product_id - 1) // len(CATEGORIES)
            base_name = ELECTRONICS_NAMES[group_index % len(ELECTRONICS_NAMES)]
        else:
            base_name = category.removesuffix("s")
        products.append(
            {
                "product_id": product_id,
                # 空格可被standard tokenizer稳定拆分；下划线可能把整串视为一个词元。
                "name": f"{base_name} model {product_id:03d}",
                "category": category,
                "price": round(50.0 + product_id * 25.5, 2),
                "stock": (product_id * 7) % 101,
                "release_date": (
                    f"2026-{(product_id - 1) % 12 + 1:02d}-"
                    f"{(product_id - 1) % 28 + 1:02d}"
                ),
            }
        )
    return tuple(products)


EXERCISE_PRODUCTS = build_exercise_products()

INDEX_MAPPINGS = {
    "properties": {
        "product_id": {"type": "integer"},
        "name": {"type": "text"},
        "category": {"type": "keyword"},
        "price": {"type": "float"},
        "stock": {"type": "integer"},
        "release_date": {"type": "date"},
    }
}


def _mapping_properties(client: Elasticsearch, index_name: str) -> dict[str, object]:
    """读取真实索引的字段映射；兼容ES返回实际索引名作为最外层键。"""

    raw = client.indices.get_mapping(index=index_name)
    index_mapping = next(iter(raw.values()))
    return dict(index_mapping.get("mappings", {}).get("properties", {}))


def _assert_mapping_contract(client: Elasticsearch, index_name: str) -> None:
    """同名索引映射不完全一致时失败，不删除或偷偷重建。"""

    expected = INDEX_MAPPINGS["properties"]
    actual = _mapping_properties(client, index_name)
    expected_types = {name: config["type"] for name, config in expected.items()}
    actual_types = {name: config.get("type") for name, config in actual.items()}
    if actual_types != expected_types:
        raise RuntimeError(
            f"索引 {index_name} 的mapping不符合练习合同；"
            f"expected={expected_types}, actual={actual_types}。为保护未知数据，程序拒绝删除索引。"
        )


def _read_existing_documents(
    client: Elasticsearch,
    index_name: str,
) -> tuple[int, dict[int, dict[str, object]]]:
    """读取最多101条，以便发现本应只有100条的额外文档。"""

    response = client.search(
        index=index_name,
        size=101,
        query={"match_all": {}},
        sort=[{"product_id": {"order": "asc"}}],
    )
    raw_total = response.get("hits", {}).get("total", 0)
    total = (
        int(raw_total.get("value", 0))
        if isinstance(raw_total, dict)
        else int(raw_total)
    )
    documents: dict[int, dict[str, object]] = {}
    for hit in response.get("hits", {}).get("hits", []):
        source = dict(hit.get("_source", {}))
        document_id = int(hit.get("_id"))
        if int(source.get("product_id", -1)) != document_id:
            raise RuntimeError(
                f"索引 {index_name} 的文档_id={document_id}与product_id不一致；拒绝继续。"
            )
        documents[document_id] = source
    return total, documents


def _assert_document_ownership(
    client: Elasticsearch,
    index_name: str,
    *,
    require_complete: bool,
) -> None:
    """只允许固定ID 1～100；最终验收还要求字段和值逐项准确。"""

    expected_by_id = {int(item["product_id"]): item for item in EXERCISE_PRODUCTS}
    total, actual_by_id = _read_existing_documents(client, index_name)
    if total != len(actual_by_id):
        raise RuntimeError(
            f"索引 {index_name} 实际文档数为{total}，超出可验证的本作业文档；拒绝继续。"
        )
    unexpected_ids = sorted(set(actual_by_id) - set(expected_by_id))
    if unexpected_ids:
        raise RuntimeError(
            f"索引 {index_name} 含未知文档ID {unexpected_ids}；为保护未知数据，程序拒绝继续。"
        )
    # 编号相同不代表内容属于本作业。写入前逐项核对，保留不符的旧文档。
    # Python的1000 == 1000.0为真，因此还必须比较type，不能只用字典相等。
    for document_id, actual in actual_by_id.items():
        expected = expected_by_id[document_id]
        if set(actual) != set(expected) or any(
            type(actual[field]) is not type(expected[field]) or actual[field] != expected[field]
            for field in expected
        ):
            raise RuntimeError(
                f"索引 {index_name} 的文档{document_id}字段、值或类型不符合固定合同；拒绝覆盖。"
            )
    if require_complete and actual_by_id != expected_by_id:
        missing_ids = sorted(set(expected_by_id) - set(actual_by_id))
        raise RuntimeError(
            f"索引 {index_name} 写入后仍不符合100条固定数据合同；missing={missing_ids}"
        )


def prepare_index(client: Elasticsearch, index_name: str) -> int:
    """验证所有权后按稳定ID写入100条数据，并执行写后强校验。"""

    if not client.indices.exists(index=index_name):
        client.indices.create(index=index_name, mappings=INDEX_MAPPINGS)
    _assert_mapping_contract(client, index_name)
    _assert_document_ownership(client, index_name, require_complete=False)
    for product in EXERCISE_PRODUCTS:
        client.index(index=index_name, id=product["product_id"], document=product)
    client.indices.refresh(index=index_name)
    _assert_document_ownership(client, index_name, require_complete=True)
    return len(EXERCISE_PRODUCTS)


def main() -> None:
    """命令行入口。"""

    settings = Settings.from_env()
    client = Elasticsearch(settings.es_url, request_timeout=10)
    count = prepare_index(client, settings.exercise_index)
    print(f"索引准备完成：{settings.exercise_index}，固定数据 {count} 条")


if __name__ == "__main__":
    main()
