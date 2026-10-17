"""固定的虚构银行数据，保证离线测试与功能演示每次结果一致。"""

from .models import Customer, Product, RetrievalHit

CUSTOMERS: tuple[Customer, ...] = (
    Customer("C001", "张三", "R1", 5_000),
    Customer("C002", "李四", "R3", 20_000),
    Customer("C003", "王五", "R5", 100_000),
)

PRODUCTS: tuple[Product, ...] = (
    Product(
        "P001",
        "安心存款",
        "存款",
        "R1",
        1_000,
        "ACTIVE",
        "本金安全性较高、期限固定，适合低风险偏好的客户。",
    ),
    Product(
        "P002",
        "稳健理财",
        "理财",
        "R2",
        3_000,
        "ACTIVE",
        "以稳健资产配置为主，净值会随市场小幅波动。",
    ),
    Product(
        "P003",
        "成长基金",
        "基金",
        "R4",
        100,
        "ACTIVE",
        "主要投资成长型权益资产，收益和波动都可能较高。",
    ),
    Product(
        "P004",
        "尊享私募",
        "私募",
        "R5",
        1_000_000,
        "ACTIVE",
        "面向符合条件的高风险承受能力客户，起投金额较高。",
    ),
    Product(
        "P005",
        "旧版稳健产品",
        "理财",
        "R1",
        1_000,
        "INACTIVE",
        "该产品已经停止销售，只能用于历史查询。",
    ),
)

CUSTOMER_BY_ID = {customer.customer_id: customer for customer in CUSTOMERS}
PRODUCT_BY_ID = {product.product_id: product for product in PRODUCTS}


def product_to_hit(product: Product, *, source: str, score: float) -> RetrievalHit:
    """把产品转换成统一的检索结果，供 ES/Neo4j/离线检索共同使用。"""

    return RetrievalHit(
        source_id=product.product_id,
        title=product.name,
        content=product.description,
        score=score,
        source=source,
        product_id=product.product_id,
        metadata={
            "category": product.category,
            "risk_level": product.risk_level,
            "min_investment": product.min_investment,
            "status": product.status,
        },
    )
