"""把用户问题分成推荐、产品事实和领域外问题。

这个模块故意使用确定性关键词，而不是让大模型自由判断。原因是：拒答边界和
金融推荐入口属于安全控制，必须可测试、可复现。生产系统可在它前面增加更强的
分类器，但不能删除这个失败时默认拒绝的兜底门。
"""

from __future__ import annotations

from enum import StrEnum

from .models import Product


class QueryIntent(StrEnum):
    """本作业支持的三类问题。"""

    RECOMMENDATION = "recommendation"
    PRODUCT_FACT = "product_fact"
    OUT_OF_SCOPE = "out_of_scope"


RECOMMENDATION_TERMS = (
    "推荐",
    "适合",
    "可以买",
    "能买",
    "选择什么",
    "选什么",
    "哪些产品",
    "什么产品",
    "哪个产品",
    "哪款产品",
    "有哪些存款",
    "有哪些理财",
    "有哪些基金",
    "有什么存款",
    "有什么理财",
    "有什么基金",
    "配置",
)

BANK_DOMAIN_TERMS = (
    "银行",
    "产品",
    "存款",
    "理财",
    "基金",
    "私募",
    "投资",
    "风险",
    "起投",
    "金额",
    "本金",
    "收益",
    "在售",
    "停售",
    "特点",
    "介绍",
)


def classify_query(question: str, products: tuple[Product, ...]) -> QueryIntent:
    """根据明确词语分类；没有银行领域证据时默认拒答。"""

    normalized = question.strip().casefold()
    product_terms = tuple(
        term.casefold()
        for product in products
        for term in (product.product_id, product.name, product.category)
    )
    if not any(term in normalized for term in BANK_DOMAIN_TERMS + product_terms):
        return QueryIntent.OUT_OF_SCOPE
    if any(term in normalized for term in RECOMMENDATION_TERMS):
        return QueryIntent.RECOMMENDATION
    return QueryIntent.PRODUCT_FACT


def select_fact_product_ids(question: str, products: tuple[Product, ...]) -> set[str]:
    """从问题中找明确产品；若只写品类，则返回该品类下的全部产品ID。"""

    normalized = question.strip().casefold()
    exact_products = {
        product.product_id
        for product in products
        if product.product_id.casefold() in normalized or product.name.casefold() in normalized
    }
    if exact_products:
        return exact_products
    return {
        product.product_id
        for product in products
        if product.category.casefold() in normalized
    }
