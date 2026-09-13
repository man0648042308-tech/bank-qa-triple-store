"""银行推荐必须先通过的确定性业务规则。

大模型可以负责组织语言，但不能决定客户是否有资格购买产品。风险、金额和销售状态
都由普通 Python 代码检查，因此结果可测试、可解释，也不会随提示词变化。
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import Customer, Product

RISK_RANK = {"R1": 1, "R2": 2, "R3": 3, "R4": 4, "R5": 5}
ACTIVE_STATUS = "ACTIVE"


@dataclass(frozen=True, slots=True)
class EligibilityDecision:
    """一项产品资格判断的结果。"""

    allowed: bool
    reasons: tuple[str, ...]


def risk_rank(risk_level: str) -> int:
    """把 ``R1``～``R5`` 转成可比较的整数，不认识的等级直接报错。"""

    try:
        return RISK_RANK[risk_level.upper()]
    except KeyError as exc:
        raise ValueError(f"未知风险等级：{risk_level!r}") from exc


def check_product_eligibility(customer: Customer, product: Product) -> EligibilityDecision:
    """依次检查销售状态、风险等级和可投资金额。"""

    reasons: list[str] = []
    if product.status.upper() != ACTIVE_STATUS:
        reasons.append("产品当前不在售")
    if risk_rank(product.risk_level) > risk_rank(customer.risk_level):
        reasons.append("产品风险高于客户风险承受等级")
    if product.min_investment > customer.available_amount:
        reasons.append("客户可用金额低于产品起投金额")
    return EligibilityDecision(allowed=not reasons, reasons=tuple(reasons))


def filter_eligible_products(customer: Customer, products: list[Product]) -> list[Product]:
    """保留所有通过硬规则的产品，同时保持输入列表的原始顺序。"""

    return [
        product
        for product in products
        if check_product_eligibility(customer, product).allowed
    ]

