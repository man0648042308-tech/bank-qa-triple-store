"""Day37半闭卷练习。

这里故意保留TODO。它不是提交版答案，也不会被生产测试导入。
请根据README逐步实现，不要直接复制exercise05中的函数体。
"""

from typing import Any


def build_product_search_body(
    *,
    keyword: str | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    category: str | None = None,
) -> dict[str, Any]:
    """根据四个可选参数构造ES查询体。"""

    # TODO 1：建立must_clauses列表。
    # TODO 2：建立filter_clauses列表。
    # TODO 3：处理keyword。
    # TODO 4：处理min_price和max_price，特别注意0与None不同。
    # TODO 5：处理category。
    # TODO 6：返回完整的query/highlight/size/sort字典。
    raise NotImplementedError("请完成半闭卷练习")


if __name__ == "__main__":
    print(
        build_product_search_body(
            keyword="phone",
            min_price=0,
            max_price=5000,
            category="electronics",
        )
    )
