"""命令行入口和真实服务组装代码。"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass

from elasticsearch import Elasticsearch
from neo4j import GraphDatabase
from redis import Redis

from .answer_generator import DeterministicAnswerGenerator
from .cache import RedisTextCache
from .elasticsearch_retriever import ElasticsearchBankRetriever
from .neo4j_repository import Neo4jCandidateRetriever, Neo4jProfileRepository
from .pipeline import BankQAPipeline, build_offline_pipeline
from .settings import Settings


@dataclass(frozen=True, slots=True)
class ServiceClients:
    """真实数据库客户端集合，便于API和命令行复用同一组连接。"""

    es: Elasticsearch
    redis: Redis
    neo4j: object


def build_service_clients(settings: Settings) -> ServiceClients:
    """只创建客户端对象；是否连通由实际查询或验证脚本决定。"""

    # 课程Day37隔离容器使用 ``NEO4J_AUTH=none``，所以密码为空时传 ``auth=None``；
    # 若以后连接启用认证的服务，只需通过进程环境变量提供密码，无需改源码。
    neo4j_auth = (
        (settings.neo4j_user, settings.neo4j_password)
        if settings.neo4j_password
        else None
    )
    return ServiceClients(
        es=Elasticsearch(settings.es_url, request_timeout=10),
        redis=Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            db=settings.redis_db,
            decode_responses=True,
            socket_timeout=5,
        ),
        neo4j=GraphDatabase.driver(
            settings.neo4j_uri,
            auth=neo4j_auth,
        ),
    )


def build_online_pipeline(
    settings: Settings,
    *,
    clients: ServiceClients | None = None,
) -> BankQAPipeline:
    """把真实ES、Redis和Neo4j适配器组装成同一条问答流水线。"""

    selected_clients = clients or build_service_clients(settings)
    return BankQAPipeline(
        customer_repository=Neo4jProfileRepository(selected_clients.neo4j),
        text_retriever=ElasticsearchBankRetriever(selected_clients.es, settings.es_index),
        graph_retriever=Neo4jCandidateRetriever(selected_clients.neo4j),
        answer_generator=DeterministicAnswerGenerator(),
        cache=RedisTextCache(selected_clients.redis),
        cache_ttl_seconds=settings.cache_ttl_seconds,
        data_version=settings.data_version,
    )


def build_parser() -> argparse.ArgumentParser:
    """定义CLI参数；默认离线，必须显式写 ``--online`` 才访问虚拟机。"""

    parser = argparse.ArgumentParser(description="Day37 银行智能问答系统")
    parser.add_argument("--customer-id", default="C001", help="固定演示客户编号")
    parser.add_argument("--question", default="我有5000元，请推荐稳健产品", help="客户问题")
    parser.add_argument("--top-k", type=int, default=5, help="最多返回多少个合规产品")
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--online", action="store_true", help="连接虚拟机中的真实数据库")
    mode_group.add_argument(
        "--offline",
        action="store_true",
        help="显式使用固定数据；即使不写该参数，默认也是离线模式",
    )
    return parser


def main() -> None:
    """运行一次问答并以UTF-8友好的JSON格式打印结果。"""

    args = build_parser().parse_args()
    settings = Settings.from_env()
    pipeline = build_online_pipeline(settings) if args.online else build_offline_pipeline()
    answer = pipeline.ask(args.customer_id, args.question, top_k=args.top_k)
    print(json.dumps(answer.to_dict(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
