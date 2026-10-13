"""Neo4j客户画像与图候选读取。

查询字符串中的 ``$customer_id`` 是参数占位符。真正的值通过驱动参数单独传入，
而不是拼接到Cypher中，这样可以避免引号错误和Cypher注入。
"""

from __future__ import annotations

from typing import Protocol

from .models import Customer, RetrievalHit
from .sample_data import CUSTOMER_BY_ID, PRODUCT_BY_ID, product_to_hit

CUSTOMER_PROFILE_QUERY = """
MATCH (c:Day37Customer {customer_id: $customer_id, dataset_id: 'day37'})
RETURN c.customer_id AS customer_id,
       c.name AS name,
       c.risk_level AS risk_level,
       toInteger(c.available_amount) AS available_amount
LIMIT 1
""".strip()

GRAPH_CANDIDATES_QUERY = """
MATCH (c:Day37Customer {customer_id: $customer_id, dataset_id: 'day37'})-[r]->
      (p:Day37Product {dataset_id: 'day37'})
WHERE r.dataset_id = 'day37'
RETURN p.product_id AS product_id,
       p.name AS name,
       p.category AS category,
       p.risk_level AS risk_level,
       toInteger(p.min_investment) AS min_investment,
       p.status AS status,
       p.description AS description,
       coalesce(r.weight, 1.0) AS graph_score
ORDER BY graph_score DESC, product_id ASC
LIMIT $top_k
""".strip()


class CustomerRepository(Protocol):
    """按客户编号读取客户画像的接口。"""

    def get_customer(self, customer_id: str) -> Customer | None: ...


class GraphRetriever(Protocol):
    """按客户关系读取图候选的接口。"""

    def search(self, customer_id: str, query: str, *, top_k: int = 10) -> list[RetrievalHit]: ...


class Neo4jProfileRepository:
    """使用Neo4j驱动参数化读取客户画像。"""

    def __init__(self, driver: object, database: str = "neo4j") -> None:
        self._driver = driver
        self._database = database

    def get_customer(self, customer_id: str) -> Customer | None:
        records, _, _ = self._driver.execute_query(  # type: ignore[attr-defined]
            CUSTOMER_PROFILE_QUERY,
            customer_id=customer_id,
            database_=self._database,
        )
        if not records:
            return None
        record = records[0]
        return Customer(
            customer_id=str(record["customer_id"]),
            name=str(record["name"]),
            risk_level=str(record["risk_level"]),
            available_amount=int(record["available_amount"]),
        )


class Neo4jCandidateRetriever:
    """读取客户在图谱中已经建立关系的产品候选。"""

    def __init__(self, driver: object, database: str = "neo4j") -> None:
        self._driver = driver
        self._database = database

    def search(self, customer_id: str, query: str, *, top_k: int = 10) -> list[RetrievalHit]:
        del query  # 当前图召回依赖客户关系，问题文本由ES负责；显式删除表示有意未使用。
        records, _, _ = self._driver.execute_query(  # type: ignore[attr-defined]
            GRAPH_CANDIDATES_QUERY,
            customer_id=customer_id,
            top_k=top_k,
            database_=self._database,
        )
        return [
            RetrievalHit(
                source_id=str(record["product_id"]),
                title=str(record["name"]),
                content=str(record.get("description") or ""),
                score=float(record.get("graph_score") or 0.0),
                source="neo4j",
                product_id=str(record["product_id"]),
                metadata={
                    "category": record.get("category", ""),
                    "risk_level": record.get("risk_level", ""),
                    "min_investment": int(record.get("min_investment") or 0),
                    "status": record.get("status", ""),
                },
            )
            for record in records
        ]


class FixtureCustomerRepository:
    """固定客户仓库，供离线运行和单元测试使用。"""

    def get_customer(self, customer_id: str) -> Customer | None:
        return CUSTOMER_BY_ID.get(customer_id)


class FixtureGraphRetriever:
    """固定图关系：不同客户拥有不同偏好顺序。"""

    _PREFERENCES = {
        "C001": ("P001", "P002", "P003"),
        "C002": ("P002", "P003", "P001"),
        "C003": ("P004", "P003", "P002"),
    }

    def search(self, customer_id: str, query: str, *, top_k: int = 10) -> list[RetrievalHit]:
        del query
        product_ids = self._PREFERENCES.get(customer_id, ())
        return [
            product_to_hit(PRODUCT_BY_ID[product_id], source="neo4j", score=1.0 / rank)
            for rank, product_id in enumerate(product_ids[:top_k], start=1)
        ]

