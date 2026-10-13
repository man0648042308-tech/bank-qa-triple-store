"""Redis缓存与离线内存缓存。

缓存只保存问答结果的 JSON 字符串。缓存键同时包含客户编号、客户画像指纹、
产品目录指纹、数据版本和问题摘要，所以画像或产品状态变化后不会复用旧答案。
"""

from __future__ import annotations

import hashlib
import time
import unicodedata
from collections.abc import Callable
from typing import Protocol


class TextCache(Protocol):
    """流水线需要的最小缓存接口，Redis和内存实现都遵守它。"""

    def get(self, key: str) -> str | None: ...

    def set(self, key: str, value: str, ttl_seconds: int) -> None: ...


def normalize_question(question: str) -> str:
    """统一全角/半角、大小写和多余空格，使等价问题得到相同摘要。"""

    normalized = unicodedata.normalize("NFKC", question).strip().casefold()
    return " ".join(normalized.split())


def build_cache_key(
    customer_id: str,
    question: str,
    data_version: str = "v1",
    *,
    profile_fingerprint: str = "",
    catalog_fingerprint: str = "",
) -> str:
    """生成客户、画像和目录隔离的键；原始问题只保留不可逆摘要。"""

    safe_customer_id = unicodedata.normalize("NFKC", customer_id).strip().upper()
    if not safe_customer_id:
        raise ValueError("customer_id 不能为空")
    normalized_question = normalize_question(question)
    if not normalized_question:
        raise ValueError("question 不能为空")
    key_material = "\n".join(
        (normalized_question, profile_fingerprint, catalog_fingerprint)
    )
    digest = hashlib.sha256(key_material.encode("utf-8")).hexdigest()
    return f"day37:qa:{data_version}:{safe_customer_id}:{digest}"


class InMemoryTTLCache:
    """无需外部服务的教学缓存，支持注入时钟以便稳定测试过期逻辑。"""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._items: dict[str, tuple[float, str]] = {}

    def get(self, key: str) -> str | None:
        item = self._items.get(key)
        if item is None:
            return None
        expires_at, value = item
        if self._clock() >= expires_at:
            # 内存版可以安全删除本进程中的过期项；不会触碰远程数据库。
            self._items.pop(key, None)
            return None
        return value

    def set(self, key: str, value: str, ttl_seconds: int) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds 必须大于 0")
        self._items[key] = (self._clock() + ttl_seconds, value)


class RedisTextCache:
    """对 ``redis.Redis`` 客户端的薄封装，便于替换成测试假对象。"""

    def __init__(self, client: object) -> None:
        self._client = client

    def get(self, key: str) -> str | None:
        value = self._client.get(key)  # type: ignore[attr-defined]
        if value is None:
            return None
        return value.decode("utf-8") if isinstance(value, bytes) else str(value)

    def set(self, key: str, value: str, ttl_seconds: int) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds 必须大于 0")
        # ``ex`` 让 Redis 自动清理过期项，避免作业演示不断留下永久键。
        self._client.set(key, value, ex=ttl_seconds)  # type: ignore[attr-defined]



