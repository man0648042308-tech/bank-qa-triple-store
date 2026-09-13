"""真实Redis验收：写入一个60秒自动过期的唯一键，不删除既有远端资源。"""

from __future__ import annotations

from uuid import uuid4

from redis import Redis

from day37_bank_qa.cache import RedisTextCache
from day37_bank_qa.settings import Settings


def main() -> None:
    settings = Settings.from_env()
    client = Redis(
        host=settings.redis_host,
        port=settings.redis_port,
        db=settings.redis_db,
        decode_responses=True,
        socket_timeout=5,
    )
    if not client.ping():
        raise RuntimeError(f"Redis不可达：{settings.redis_host}:{settings.redis_port}")

    key = f"day37:verification:{uuid4().hex}"
    cache = RedisTextCache(client)
    cache.set(key, "redis-ok", ttl_seconds=60)
    assert cache.get(key) == "redis-ok"
    ttl = client.ttl(key)
    assert 0 < ttl <= 60
    print(f"REDIS_VERIFY_PASS key={key} ttl={ttl}")


if __name__ == "__main__":
    main()

