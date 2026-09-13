from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from day37_bank_qa.api import create_app

API_KEY = "unit-test-api-key"
AUTH_HEADERS = {"X-API-Key": API_KEY}


def test_health_search_and_question_answer_endpoints() -> None:
    client = TestClient(create_app(api_key=API_KEY))

    health = client.get("/health", headers=AUTH_HEADERS)
    search = client.get(
        "/products/search",
        params={"keyword": "安心", "max_price": 5000.5},
        headers=AUTH_HEADERS,
    )
    answer = client.post(
        "/qa/ask",
        json={"customer_id": "C001", "question": "推荐稳健产品", "top_k": 3},
        headers=AUTH_HEADERS,
    )

    assert health.status_code == 200
    assert health.json() == {"status": "ok", "mode": "offline"}
    assert search.status_code == 200
    assert search.json()["total"] == 1
    assert search.json()["items"][0]["highlighted_name"] == "<em>安心</em>存款"
    assert answer.status_code == 200
    assert answer.json()["customer_id"] == "C001"
    assert answer.json()["recommended_product_ids"] == ["P001"]


def test_api_reports_unknown_customer_and_invalid_input() -> None:
    client = TestClient(create_app(api_key=API_KEY))

    missing_customer = client.post(
        "/qa/ask",
        json={"customer_id": "C404", "question": "推荐产品"},
        headers=AUTH_HEADERS,
    )
    empty_question = client.post(
        "/qa/ask",
        json={"customer_id": "C001", "question": ""},
        headers=AUTH_HEADERS,
    )
    reversed_price = client.get(
        "/products/search",
        params={"min_price": 9000, "max_price": 100},
        headers=AUTH_HEADERS,
    )
    too_long = client.post(
        "/qa/ask",
        json={"customer_id": "C001", "question": "产品" * 251},
        headers=AUTH_HEADERS,
    )

    assert missing_customer.status_code == 404
    assert empty_question.status_code == 422
    assert reversed_price.status_code == 422
    assert too_long.status_code == 422


def test_all_business_endpoints_require_the_correct_api_key() -> None:
    client = TestClient(create_app(api_key=API_KEY))

    for method, path in (
        ("get", "/health"),
        ("get", "/products/search"),
        ("post", "/qa/ask"),
    ):
        request = getattr(client, method)
        kwargs = (
            {"json": {"customer_id": "C001", "question": "推荐产品"}}
            if method == "post"
            else {}
        )
        assert request(path, **kwargs).status_code == 401
        assert request(path, headers={"X-API-Key": "wrong"}, **kwargs).status_code == 401

    assert client.get("/health", headers=AUTH_HEADERS).status_code == 200


def test_missing_server_api_key_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DAY37_API_KEY", raising=False)
    client = TestClient(create_app(api_key=None))

    response = client.get("/health", headers={"X-API-Key": "anything"})

    assert response.status_code == 503


def test_openapi_declares_api_key_security_scheme() -> None:
    schema = create_app(api_key=API_KEY).openapi()

    schemes = schema["components"]["securitySchemes"]
    assert schemes["APIKeyHeader"]["type"] == "apiKey"
    assert schemes["APIKeyHeader"]["name"] == "X-API-Key"
    assert schemes["APIKeyHeader"]["in"] == "header"
