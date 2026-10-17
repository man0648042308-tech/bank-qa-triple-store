"""示例五命令行演示：输入可选条件并打印总命中数、高亮名称和相关度。"""

from __future__ import annotations

import argparse

from elasticsearch import Elasticsearch

from day37_bank_qa.settings import Settings

from .search_products import ElasticsearchProductSearch


def build_parser() -> argparse.ArgumentParser:
    """定义命令行参数；不填写的条件会保持为 ``None``。"""

    parser = argparse.ArgumentParser(description="运行Day37 Elasticsearch示例五")
    parser.add_argument("--keyword", help="产品名称关键词，例如：稳健")
    parser.add_argument("--min-price", type=float, help="最低价格（含边界，可带小数）")
    parser.add_argument("--max-price", type=float, help="最高价格（含边界，可带小数）")
    parser.add_argument("--category", help="精确品类，例如：理财")
    return parser


def main() -> None:
    """连接项目虚拟机ES并运行查询。"""

    args = build_parser().parse_args()
    settings = Settings.from_env()
    client = Elasticsearch(settings.es_url, request_timeout=10)
    response = ElasticsearchProductSearch(client, settings.exercise_index).search_products(
        keyword=args.keyword,
        min_price=args.min_price,
        max_price=args.max_price,
        category=args.category,
    )
    print(f"总命中数：{response.total}")
    for item in response.items:
        print(
            f"{item.product_id} | {item.highlighted_name} | "
            f"{item.category} | {item.price:.2f}元 | 库存{item.stock} | score={item.score:.4f}"
        )


if __name__ == "__main__":
    main()
