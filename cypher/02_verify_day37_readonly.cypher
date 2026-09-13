// Day37 Neo4j 只读验收脚本
//
// 本文件只有 MATCH、CALL、WITH、RETURN，不包含 CREATE、MERGE、SET、DELETE。
// 目标是验证：数量正确、固定数据合同没有分叉、所有 Day37 节点/关系都有 dataset_id。

// 子查询 1：统计客户数量，并检查三个客户的关键值是否准确。
CALL {
  MATCH (customer:Day37Customer {dataset_id: 'day37'})
  WITH customer ORDER BY customer.customer_id
  WITH collect([
    customer.customer_id,
    customer.name,
    customer.risk_level,
    customer.available_amount
  ]) AS actual_customers,
  count(customer) AS customer_count
  RETURN customer_count,
         actual_customers = [
           ['C001', '张三', 'R1', 5000],
           ['C002', '李四', 'R3', 20000],
           ['C003', '王五', 'R5', 100000]
         ] AS customer_contract_ok
}

// 子查询 2：统计产品数量，并逐项检查产品合同。
CALL {
  MATCH (product:Day37Product {dataset_id: 'day37'})
  WITH product ORDER BY product.product_id
  WITH collect([
    product.product_id,
    product.name,
    product.category,
    product.risk_level,
    product.min_investment,
    product.status
  ]) AS actual_products,
  count(product) AS product_count
  RETURN product_count,
         actual_products = [
           ['P001', '安心存款', '存款', 'R1', 1000, 'ACTIVE'],
           ['P002', '稳健理财', '理财', 'R2', 3000, 'ACTIVE'],
           ['P003', '成长基金', '基金', 'R4', 100, 'ACTIVE'],
           ['P004', '尊享私募', '私募', 'R5', 1000000, 'ACTIVE'],
           ['P005', '旧版稳健产品', '理财', 'R1', 1000, 'INACTIVE']
         ] AS product_contract_ok
}

// 子查询 3～5：统计分类、知识和关系。
CALL {
  MATCH (category:Day37Category {dataset_id: 'day37'})
  RETURN count(category) AS category_count
}
CALL {
  MATCH (knowledge:Day37Knowledge {dataset_id: 'day37'})
  RETURN count(knowledge) AS knowledge_count
}
CALL {
  MATCH ()-[relation {dataset_id: 'day37'}]->()
  RETURN count(relation) AS relationship_count
}

// 子查询 6：任何 Day37 标签节点都必须带 dataset_id='day37'。
CALL {
  MATCH (node)
  WHERE any(label_name IN labels(node) WHERE label_name STARTS WITH 'Day37')
    AND (node.dataset_id IS NULL OR node.dataset_id <> 'day37')
  RETURN count(node) AS bad_node_dataset_count
}

// 子查询 7：Day37 节点之间的作业关系也必须带正确 dataset_id。
CALL {
  MATCH (left_node)-[relation]->(right_node)
  WHERE any(label_name IN labels(left_node) WHERE label_name STARTS WITH 'Day37')
    AND any(label_name IN labels(right_node) WHERE label_name STARTS WITH 'Day37')
    AND (relation.dataset_id IS NULL OR relation.dataset_id <> 'day37')
  RETURN count(relation) AS bad_relation_dataset_count
}

// 所有硬门槛同时满足才输出 PASS，否则输出 FAIL。
RETURN customer_count,
       product_count,
       category_count,
       knowledge_count,
       relationship_count,
       customer_contract_ok,
       product_contract_ok,
       bad_node_dataset_count,
       bad_relation_dataset_count,
       CASE
         WHEN customer_count = 3
          AND product_count = 5
          AND category_count = 4
          AND knowledge_count = 5
          AND relationship_count = 16
          AND customer_contract_ok
          AND product_contract_ok
          AND bad_node_dataset_count = 0
          AND bad_relation_dataset_count = 0
         THEN 'PASS'
         ELSE 'FAIL'
       END AS verification_result;
