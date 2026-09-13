"""真实全链路验收：ES + Neo4j + Redis；不删除任何远端资源。"""

from __future__ import annotations

from uuid import uuid4

from day37_bank_qa.main import build_online_pipeline, build_service_clients
from day37_bank_qa.settings import Settings


def main() -> None:
    settings = Settings.from_env()
    clients = build_service_clients(settings)
    try:
        pipeline = build_online_pipeline(settings, clients=clients)
        # 唯一后缀保证脚本重复运行时仍能观察“首次未命中、第二次命中”；
        # 不使用 FLUSHDB，也不删除其他人的缓存键。
        question = f"请推荐适合低风险客户的稳健产品 验收批次{uuid4().hex[:8]}"
        first = pipeline.ask("C001", question, top_k=5)
        second = pipeline.ask("C001", question, top_k=5)

        assert first.cache_hit is False, "首次查询应执行真实检索"
        assert second.cache_hit is True, "第二次相同查询应命中Redis"
        assert first.recommended_product_ids == ("P001",), (
            "C001为R1且有5000元，只能推荐在售、金额足够的R1产品P001"
        )
        assert first.sources, "回答必须有来源"
        assert any("elasticsearch" in source for source in first.sources), (
            "完整链必须证明Elasticsearch提供了证据"
        )
        assert any("neo4j" in source for source in first.sources), (
            "完整链必须证明Neo4j提供了图候选"
        )
        print(
            "FULL_VERIFY_PASS "
            f"products={first.recommended_product_ids} cache_second={second.cache_hit}"
        )
    finally:
        clients.neo4j.close()  # type: ignore[attr-defined]
        clients.es.close()
        clients.redis.close()


if __name__ == "__main__":
    main()
