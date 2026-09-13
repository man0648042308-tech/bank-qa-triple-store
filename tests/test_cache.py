from __future__ import annotations

import pytest

from day37_bank_qa.cache import (
    InMemoryTTLCache,
    RedisTextCache,
    build_cache_key,
    normalize_question,
)


def test_cache_key_is_normalized_but_isolated_by_customer_and_version() -> None:
    first = build_cache_key("C001", "  推荐   稳健产品 ", "v1")
    same_question = build_cache_key("c001", "推荐 稳健产品", "v1")
    other_customer = build_cache_key("C002", "推荐 稳健产品", "v1")
    other_version = build_cache_key("C001", "推荐 稳健产品", "v2")
    other_profile = build_cache_key(
        "C001",
        "推荐 稳健产品",
        "v1",
        profile_fingerprint="R2|5000",
    )
    other_catalog = build_cache_key(
        "C001",
        "推荐 稳健产品",
        "v1",
        catalog_fingerprint="catalog-v2",
    )

    assert first == same_question
    assert first != other_customer
    assert first != other_version
    assert first != other_profile
    assert first != other_catalog
    assert "推荐" not in first
    assert normalize_question("Ａ  B") == "a b"


@pytest.mark.parametrize(("customer_id", "question"), [("", "问题"), ("C001", "  ")])
def test_cache_key_rejects_empty_identity_or_question(customer_id: str, question: str) -> None:
    with pytest.raises(ValueError):
        build_cache_key(customer_id, question)


def test_in_memory_cache_expires_deterministically() -> None:
    now = [100.0]
    cache = InMemoryTTLCache(clock=lambda: now[0])
    cache.set("key", "value", ttl_seconds=10)

    assert cache.get("key") == "value"
    now[0] = 110.0
    assert cache.get("key") is None


class FakeRedis:
    def __init__(self) -> None:
        self.value: bytes | None = None
        self.last_set: tuple[str, str, int] | None = None

    def get(self, key: str) -> bytes | None:
        del key
        return self.value

    def set(self, key: str, value: str, *, ex: int) -> None:
        self.last_set = (key, value, ex)


def test_redis_adapter_uses_expiration_and_decodes_bytes() -> None:
    client = FakeRedis()
    cache = RedisTextCache(client)
    client.value = "中文".encode()

    assert cache.get("key") == "中文"
    cache.set("key", "value", ttl_seconds=60)
    assert client.last_set == ("key", "value", 60)
