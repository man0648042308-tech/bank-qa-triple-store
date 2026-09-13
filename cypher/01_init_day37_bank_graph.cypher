// Day37 银行智能问答系统：Neo4j 初始化脚本
//
// 整体作用：
// 1. 创建 3 个虚构客户、5 个银行产品、4 个产品分类、5 条产品知识；
// 2. 建立客户兴趣/浏览、产品分类、知识来源关系；
// 3. 所有节点和关系都带 dataset_id='day37'，与其他作业数据隔离。
//
// 安全说明：
// - 本文件没有 MATCH (n) DETACH DELETE n，也不会清理其他数据。
// - MERGE 表示“找到就复用，找不到才创建”，所以重复运行不会无限复制数据。
// - 此处均为虚构数据，不包含真实客户个人信息。

// -------------------- 第 1 步：客户节点 --------------------
// UNWIND 把列表中的三个字典逐个取出，每次把当前字典命名为 row。
UNWIND [
  {customer_id: 'C001', name: '张三', risk_level: 'R1', available_amount: 5000},
  {customer_id: 'C002', name: '李四', risk_level: 'R3', available_amount: 20000},
  {customer_id: 'C003', name: '王五', risk_level: 'R5', available_amount: 100000}
] AS row
// :Day37Customer 是节点标签；花括号内是用于唯一定位本作业客户的属性。
MERGE (customer:Day37Customer {
  dataset_id: 'day37',
  customer_id: row.customer_id
})
// SET 把当前 row 中的值写入已经找到或刚创建的 customer 节点。
SET customer.name = row.name,
    customer.risk_level = row.risk_level,
    customer.available_amount = row.available_amount;

// -------------------- 第 2 步：产品节点 --------------------
// 下面字段与 Python 的 sample_data.py 完全一致，避免两个数据源“看起来相同、实际不同”。
UNWIND [
  {
    product_id: 'P001',
    name: '安心存款',
    category: '存款',
    risk_level: 'R1',
    min_investment: 1000,
    status: 'ACTIVE',
    description: '本金安全性较高、期限固定，适合低风险偏好的客户。'
  },
  {
    product_id: 'P002',
    name: '稳健理财',
    category: '理财',
    risk_level: 'R2',
    min_investment: 3000,
    status: 'ACTIVE',
    description: '以稳健资产配置为主，净值会随市场小幅波动。'
  },
  {
    product_id: 'P003',
    name: '成长基金',
    category: '基金',
    risk_level: 'R4',
    min_investment: 100,
    status: 'ACTIVE',
    description: '主要投资成长型权益资产，收益和波动都可能较高。'
  },
  {
    product_id: 'P004',
    name: '尊享私募',
    category: '私募',
    risk_level: 'R5',
    min_investment: 1000000,
    status: 'ACTIVE',
    description: '面向符合条件的高风险承受能力客户，起投金额较高。'
  },
  {
    product_id: 'P005',
    name: '旧版稳健产品',
    category: '理财',
    risk_level: 'R1',
    min_investment: 1000,
    status: 'INACTIVE',
    description: '该产品已经停止销售，只能用于历史查询。'
  }
] AS row
MERGE (product:Day37Product {
  dataset_id: 'day37',
  product_id: row.product_id
})
SET product.name = row.name,
    product.category = row.category,
    product.risk_level = row.risk_level,
    product.min_investment = row.min_investment,
    product.status = row.status,
    product.description = row.description;

// -------------------- 第 3 步：分类节点 --------------------
UNWIND [
  {category_id: 'CAT_DEPOSIT', name: '存款'},
  {category_id: 'CAT_WEALTH', name: '理财'},
  {category_id: 'CAT_FUND', name: '基金'},
  {category_id: 'CAT_PRIVATE', name: '私募'}
] AS row
MERGE (category:Day37Category {
  dataset_id: 'day37',
  category_id: row.category_id
})
SET category.name = row.name;

// -------------------- 第 4 步：产品属于哪个分类 --------------------
UNWIND [
  {product_id: 'P001', category_id: 'CAT_DEPOSIT'},
  {product_id: 'P002', category_id: 'CAT_WEALTH'},
  {product_id: 'P003', category_id: 'CAT_FUND'},
  {product_id: 'P004', category_id: 'CAT_PRIVATE'},
  {product_id: 'P005', category_id: 'CAT_WEALTH'}
] AS row
MATCH (product:Day37Product {dataset_id: 'day37', product_id: row.product_id})
MATCH (category:Day37Category {dataset_id: 'day37', category_id: row.category_id})
// -[:BELONGS_TO]-> 是一条有方向的关系：产品指向分类。
MERGE (product)-[relation:BELONGS_TO {dataset_id: 'day37'}]->(category);

// -------------------- 第 5 步：客户兴趣关系 --------------------
UNWIND [
  {customer_id: 'C001', product_id: 'P001'},
  {customer_id: 'C002', product_id: 'P002'},
  {customer_id: 'C003', product_id: 'P003'}
] AS row
MATCH (customer:Day37Customer {dataset_id: 'day37', customer_id: row.customer_id})
MATCH (product:Day37Product {dataset_id: 'day37', product_id: row.product_id})
MERGE (customer)-[relation:INTERESTED_IN {dataset_id: 'day37'}]->(product);

// -------------------- 第 6 步：客户浏览关系 --------------------
UNWIND [
  {customer_id: 'C001', product_id: 'P002'},
  {customer_id: 'C002', product_id: 'P003'},
  {customer_id: 'C003', product_id: 'P004'}
] AS row
MATCH (customer:Day37Customer {dataset_id: 'day37', customer_id: row.customer_id})
MATCH (product:Day37Product {dataset_id: 'day37', product_id: row.product_id})
MERGE (customer)-[relation:VIEWED {dataset_id: 'day37'}]->(product);

// -------------------- 第 7 步：可追溯的知识节点 --------------------
// 每条知识都对应一个产品。问答系统可以把它作为回答来源，而不是凭空编造。
UNWIND [
  {knowledge_id: 'K001', product_id: 'P001', title: '安心存款产品说明', content: '本金安全性较高、期限固定，适合低风险偏好的客户。'},
  {knowledge_id: 'K002', product_id: 'P002', title: '稳健理财产品说明', content: '以稳健资产配置为主，净值会随市场小幅波动。'},
  {knowledge_id: 'K003', product_id: 'P003', title: '成长基金产品说明', content: '主要投资成长型权益资产，收益和波动都可能较高。'},
  {knowledge_id: 'K004', product_id: 'P004', title: '尊享私募产品说明', content: '面向符合条件的高风险承受能力客户，起投金额较高。'},
  {knowledge_id: 'K005', product_id: 'P005', title: '旧版稳健产品说明', content: '该产品已经停止销售，只能用于历史查询。'}
] AS row
MERGE (knowledge:Day37Knowledge {
  dataset_id: 'day37',
  knowledge_id: row.knowledge_id
})
SET knowledge.title = row.title,
    knowledge.content = row.content
WITH knowledge, row
MATCH (product:Day37Product {dataset_id: 'day37', product_id: row.product_id})
MERGE (knowledge)-[relation:ABOUT {dataset_id: 'day37'}]->(product);

// 初始化完成后返回汇总，便于人工看到本次脚本确实执行到了最后。
MATCH (node {dataset_id: 'day37'})
RETURN count(node) AS day37_node_count;
