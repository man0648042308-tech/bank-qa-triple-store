"""真实Neo4j验收：只读取dataset_id=day37的数据，不创建或删除节点。"""

from __future__ import annotations

from neo4j import GraphDatabase

from day37_bank_qa.settings import Settings

COUNT_QUERY = """
CALL {
  MATCH (c:Day37Customer {dataset_id: $dataset_id})
  RETURN count(c) AS customer_count,
         collect([c.customer_id, c.name, c.risk_level, c.available_amount]) AS customers
}
CALL {
  MATCH (p:Day37Product {dataset_id: $dataset_id})
  RETURN count(p) AS product_count,
         collect([p.product_id, p.name, p.risk_level, p.min_investment, p.status]) AS products
}
CALL {
  MATCH (category:Day37Category {dataset_id: $dataset_id})
  RETURN count(category) AS category_count
}
CALL {
  MATCH (knowledge:Day37Knowledge {dataset_id: $dataset_id})
  RETURN count(knowledge) AS knowledge_count
}
RETURN customer_count, product_count, category_count, knowledge_count, customers, products
""".strip()

RELATION_QUERY = """
MATCH (left_node)-[r]->(right_node)
WHERE r.dataset_id = $dataset_id
  AND any(label_name IN labels(left_node) WHERE label_name STARTS WITH 'Day37')
  AND any(label_name IN labels(right_node) WHERE label_name STARTS WITH 'Day37')
RETURN count(r) AS relation_count, type(r) AS relation_type
ORDER BY relation_type
""".strip()


def main() -> None:
    settings = Settings.from_env()
    auth = (
        (settings.neo4j_user, settings.neo4j_password)
        if settings.neo4j_password
        else None
    )
    driver = GraphDatabase.driver(settings.neo4j_uri, auth=auth)
    try:
        driver.verify_connectivity()
        records, _, _ = driver.execute_query(
            COUNT_QUERY,
            dataset_id="day37",
            database_="neo4j",
        )
        relation_records, _, _ = driver.execute_query(
            RELATION_QUERY,
            dataset_id="day37",
            database_="neo4j",
        )
        customer_count = int(records[0]["customer_count"])
        product_count = int(records[0]["product_count"])
        category_count = int(records[0]["category_count"])
        knowledge_count = int(records[0]["knowledge_count"])
        relation_counts = {
            str(record["relation_type"]): int(record["relation_count"])
            for record in relation_records
        }
        relation_count = sum(relation_counts.values())
        assert customer_count == 3, f"应有3位Day37客户，实际{customer_count}"
        assert product_count == 5, f"应有5个Day37产品，实际{product_count}"
        assert category_count == 4, f"应有4个Day37分类，实际{category_count}"
        assert knowledge_count == 5, f"应有5条Day37知识，实际{knowledge_count}"
        assert relation_counts == {
            "ABOUT": 5,
            "BELONGS_TO": 5,
            "INTERESTED_IN": 3,
            "VIEWED": 3,
        }, f"关系类型或数量不符合16条固定合同：{relation_counts}"
        assert sorted(records[0]["customers"]) == [
            ["C001", "张三", "R1", 5000],
            ["C002", "李四", "R3", 20000],
            ["C003", "王五", "R5", 100000],
        ]
        assert sorted(records[0]["products"]) == [
            ["P001", "安心存款", "R1", 1000, "ACTIVE"],
            ["P002", "稳健理财", "R2", 3000, "ACTIVE"],
            ["P003", "成长基金", "R4", 100, "ACTIVE"],
            ["P004", "尊享私募", "R5", 1000000, "ACTIVE"],
            ["P005", "旧版稳健产品", "R1", 1000, "INACTIVE"],
        ]
        print(
            "NEO4J_VERIFY_PASS "
            f"customers={customer_count} products={product_count} categories={category_count} "
            f"knowledge={knowledge_count} relations={relation_count}"
        )
    finally:
        driver.close()


if __name__ == "__main__":
    main()

