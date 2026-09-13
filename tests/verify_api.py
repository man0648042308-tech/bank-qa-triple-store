"""真实API验收：连接三库，并验证X-API-Key的401/200安全边界。"""

from __future__ import annotations

import os

from fastapi.testclient import TestClient

from day37_bank_qa.api import create_app
from day37_bank_qa.main import build_online_pipeline, build_service_clients
from day37_bank_qa.settings import Settings
from exercise05.search_products import ElasticsearchProductSearch


def main() -> None:
    api_key = os.getenv("DAY37_API_KEY")
    if not api_key:
        raise RuntimeError("请只在当前PowerShell进程设置 DAY37_API_KEY 后再验收")

    settings = Settings.from_env()
    clients = build_service_clients(settings)
    try:
        pipeline = build_online_pipeline(settings, clients=clients)
        product_search = ElasticsearchProductSearch(clients.es, settings.exercise_index)
        application = create_app(
            pipeline=pipeline,
            product_search=product_search,
            mode="online",
            api_key=api_key,
        )
        client = TestClient(application)
        headers = {"X-API-Key": api_key}

        assert client.get("/health").status_code == 401
        assert client.get("/health", headers={"X-API-Key": "wrong"}).status_code == 401
        assert client.get("/health", headers=headers).json() == {
            "status": "ok",
            "mode": "online",
        }

        search = client.get(
            "/products/search",
            params={"keyword": "phone", "min_price": 100.5, "max_price": 800.75},
            headers=headers,
        )
        assert search.status_code == 200
        assert search.json()["total"] == 1

        answer = client.post(
            "/qa/ask",
            json={"customer_id": "C001", "question": "请推荐稳健产品", "top_k": 5},
            headers=headers,
        )
        assert answer.status_code == 200
        assert answer.json()["recommended_product_ids"] == ["P001"]
        print("API_VERIFY_PASS missing=401 wrong=401 correct=200 products=1 recommendation=P001")
    finally:
        clients.neo4j.close()  # type: ignore[attr-defined]
        clients.es.close()
        clients.redis.close()


if __name__ == "__main__":
    main()
