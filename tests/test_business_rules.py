from __future__ import annotations

import pytest

from day37_bank_qa.business_rules import (
    check_product_eligibility,
    filter_eligible_products,
    risk_rank,
)
from day37_bank_qa.models import Customer, Product
from day37_bank_qa.sample_data import CUSTOMER_BY_ID, PRODUCT_BY_ID


def test_active_risk_and_amount_must_all_pass() -> None:
    customer = CUSTOMER_BY_ID["C001"]

    assert check_product_eligibility(customer, PRODUCT_BY_ID["P001"]).allowed is True
    assert check_product_eligibility(customer, PRODUCT_BY_ID["P002"]).allowed is False
    assert "风险" in check_product_eligibility(customer, PRODUCT_BY_ID["P003"]).reasons[0]
    assert "不在售" in check_product_eligibility(customer, PRODUCT_BY_ID["P005"]).reasons[0]


def test_amount_failure_has_clear_reason() -> None:
    customer = Customer("C900", "测试客户", "R5", 999)
    product = Product("PX", "测试产品", "理财", "R1", 1_000, "ACTIVE", "测试")

    decision = check_product_eligibility(customer, product)

    assert decision.allowed is False
    assert decision.reasons == ("客户可用金额低于产品起投金额",)


def test_filter_keeps_original_order_and_only_eligible_products() -> None:
    result = filter_eligible_products(
        CUSTOMER_BY_ID["C002"],
        [PRODUCT_BY_ID["P003"], PRODUCT_BY_ID["P002"], PRODUCT_BY_ID["P001"]],
    )

    assert [product.product_id for product in result] == ["P002", "P001"]


def test_unknown_risk_level_fails_closed() -> None:
    with pytest.raises(ValueError, match="未知风险等级"):
        risk_rank("R9")

