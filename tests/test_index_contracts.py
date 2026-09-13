from __future__ import annotations

from copy import deepcopy

import pytest

from day37_bank_qa.prepare_bank_index import (
    BANK_INDEX_MAPPINGS,
    _bank_documents,
    prepare_bank_index,
)
from exercise05.prepare_product_index import EXERCISE_PRODUCTS, INDEX_MAPPINGS, prepare_index


class FakeIndices:
    def __init__(self, owner: FakeElasticsearch, exists: bool) -> None:
        self._owner = owner
        self._exists = exists

    def exists(self, *, index: str) -> bool:
        del index
        return self._exists

    def create(
        self,
        *,
        index: str,
        mappings: dict[str, object],
        settings: dict[str, object] | None = None,
    ) -> None:
        del index, settings
        self._exists = True
        self._owner.mapping = deepcopy(mappings)

    def get_mapping(self, *, index: str) -> dict[str, object]:
        return {index: {"mappings": deepcopy(self._owner.mapping)}}

    def refresh(self, *, index: str) -> None:
        del index


class FakeElasticsearch:
    def __init__(
        self,
        *,
        mapping: dict[str, object],
        documents: dict[str, dict[str, object]] | None = None,
        exists: bool = True,
    ) -> None:
        self.mapping = deepcopy(mapping)
        self.documents = deepcopy(documents or {})
        self.writes = 0
        self.indices = FakeIndices(self, exists)

    def search(self, **kwargs: object) -> dict[str, object]:
        size = int(kwargs["size"])
        hits = [
            {"_id": document_id, "_source": deepcopy(document)}
            for document_id, document in sorted(
                self.documents.items(), key=lambda item: int(item[0].removeprefix("P"))
            )[:size]
        ]
        return {"hits": {"total": {"value": len(self.documents)}, "hits": hits}}

    def index(self, *, index: str, id: object, document: dict[str, object]) -> None:
        del index
        self.writes += 1
        self.documents[str(id)] = deepcopy(document)


def test_exercise_index_is_created_and_finishes_with_exactly_100_documents() -> None:
    client = FakeElasticsearch(mapping={"properties": {}}, exists=False)

    count = prepare_index(client, "exercise")  # type: ignore[arg-type]

    assert count == 100
    assert len(client.documents) == 100
    assert client.documents["1"]["name"] == "phone model 001"


def test_exercise_index_rejects_wrong_mapping_without_deleting_it() -> None:
    wrong_mapping = deepcopy(INDEX_MAPPINGS)
    wrong_mapping["properties"]["price"] = {"type": "integer"}
    client = FakeElasticsearch(mapping=wrong_mapping)

    with pytest.raises(RuntimeError, match="mapping不符合"):
        prepare_index(client, "exercise")  # type: ignore[arg-type]

    assert client.mapping == wrong_mapping


def test_exercise_index_rejects_unknown_document_id() -> None:
    client = FakeElasticsearch(
        mapping=INDEX_MAPPINGS,
        documents={"999": {"product_id": 999, "name": "unknown"}},
    )

    with pytest.raises(RuntimeError, match="未知文档ID"):
        prepare_index(client, "exercise")  # type: ignore[arg-type]

    assert "999" in client.documents


def test_bank_index_rejects_unknown_document_id() -> None:
    client = FakeElasticsearch(
        mapping=BANK_INDEX_MAPPINGS,
        documents={"P999": {"product_id": "P999", "name": "unknown"}},
    )

    with pytest.raises(RuntimeError, match="未知文档ID"):
        prepare_bank_index(client, "bank")  # type: ignore[arg-type]

    assert "P999" in client.documents


@pytest.mark.parametrize("resource", ["exercise", "bank"])
@pytest.mark.parametrize("mutation", ["value", "numeric_type", "missing_field", "extra_field"])
def test_existing_known_id_with_different_content_is_rejected_before_any_write(
    resource: str, mutation: str,
) -> None:
    if resource == "exercise":
        document = deepcopy(EXERCISE_PRODUCTS[0])
        document_id = "1"
        mapping = INDEX_MAPPINGS
        prepare = prepare_index
        amount_field = "price"
    else:
        document = deepcopy(_bank_documents()["P001"])
        document_id = "P001"
        mapping = BANK_INDEX_MAPPINGS
        prepare = prepare_bank_index
        amount_field = "min_investment"
    if mutation == "value":
        document["name"] = "existing content must be preserved"
    elif mutation == "numeric_type":
        value = document[amount_field]
        document[amount_field] = int(value) if type(value) is float else float(value)
    elif mutation == "missing_field":
        document.pop("name")
    else:
        document["existing_extra"] = "must not erase"
    client = FakeElasticsearch(mapping=mapping, documents={document_id: document})
    before = deepcopy(client.documents)

    with pytest.raises(RuntimeError, match="字段、值或类型"):
        prepare(client, resource)  # type: ignore[arg-type]

    assert client.writes == 0
    assert client.documents == before
