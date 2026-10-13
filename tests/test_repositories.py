from __future__ import annotations

from day37_bank_qa.elasticsearch_retriever import ElasticsearchBankRetriever
from day37_bank_qa.neo4j_repository import (
    CUSTOMER_PROFILE_QUERY,
    GRAPH_CANDIDATES_QUERY,
    Neo4jCandidateRetriever,
    Neo4jProfileRepository,
)
from day37_bank_qa.prepare_bank_index import BANK_INDEX_MAPPINGS, BANK_INDEX_SETTINGS


class FakeNeo4jDriver:
    def __init__(self, records: list[dict[str, object]]) -> None:
        self.records = records
        self.query = ""
        self.parameters: dict[str, object] = {}

    def execute_query(self, query: str, **parameters: object) -> tuple[object, None, None]:
        self.query = query
        self.parameters = parameters
        return self.records, None, None


def test_profile_query_is_parameterized_and_day37_isolated() -> None:
    driver = FakeNeo4jDriver(
        [{"customer_id": "C001", "name": "张三", "risk_level": "R1", "available_amount": 5000}]
    )
    customer = Neo4jProfileRepository(driver).get_customer("C001")

    assert customer is not None and customer.customer_id == "C001"
    assert "$customer_id" in driver.query
    assert "C001" not in driver.query
    assert "Day37Customer" in CUSTOMER_PROFILE_QUERY
    assert "dataset_id: 'day37'" in CUSTOMER_PROFILE_QUERY
    assert driver.parameters == {"customer_id": "C001", "database_": "neo4j"}


def test_graph_query_limits_nodes_and_relationship_to_day37_dataset() -> None:
    driver = FakeNeo4jDriver(
        [
            {
                "product_id": "P001",
                "name": "安心存款",
                "category": "存款",
                "risk_level": "R1",
                "min_investment": 1000,
                "status": "ACTIVE",
                "description": "说明",
                "graph_score": 2.0,
            }
        ]
    )
    hits = Neo4jCandidateRetriever(driver).search("C001", "稳健", top_k=3)

    assert hits[0].product_id == "P001"
    assert "Day37Customer" in GRAPH_CANDIDATES_QUERY
    assert "Day37Product" in GRAPH_CANDIDATES_QUERY
    assert "r.dataset_id = 'day37'" in GRAPH_CANDIDATES_QUERY
    assert driver.parameters["customer_id"] == "C001"
    assert driver.parameters["top_k"] == 3


class FakeES:
    def __init__(self) -> None:
        self.kwargs: dict[str, object] = {}

    def search(self, **kwargs: object) -> dict[str, object]:
        self.kwargs = kwargs
        return {
            "hits": {
                "hits": [
                    {
                        "_id": "P001",
                        "_score": 4.2,
                        "_source": {
                            "product_id": "P001",
                            "name": "安心存款",
                            "description": "稳健",
                            "category": "存款",
                            "risk_level": "R1",
                            "min_investment": 1000,
                            "status": "ACTIVE",
                        },
                    }
                ]
            }
        }


def test_elasticsearch_retriever_builds_multi_match_and_maps_metadata() -> None:
    client = FakeES()
    hits = ElasticsearchBankRetriever(client, "day37_bank_knowledge_v1").search("稳健", top_k=3)

    assert client.kwargs["index"] == "day37_bank_knowledge_v1"
    assert client.kwargs["size"] == 3
    bool_query = client.kwargs["query"]["bool"]  # type: ignore[index]
    assert bool_query["must"][0]["multi_match"]["query"] == "稳健"  # type: ignore[index]
    assert bool_query["filter"] == [{"term": {"dataset_id": "day37"}}]  # type: ignore[index]
    assert hits[0].product_id == "P001"
    assert hits[0].metadata["min_investment"] == 1000


def test_bank_index_contract_uses_day37_ngram_without_ik_dependency() -> None:
    analyzer = BANK_INDEX_SETTINGS["analysis"]["analyzer"]["day37_cn_ngram"]
    mappings = BANK_INDEX_MAPPINGS["properties"]

    assert analyzer["tokenizer"] == "day37_ngram_tokenizer"
    assert mappings["dataset_id"]["type"] == "keyword"
    assert mappings["name"]["analyzer"] == "day37_cn_ngram"
    assert mappings["min_investment"]["type"] == "integer"

