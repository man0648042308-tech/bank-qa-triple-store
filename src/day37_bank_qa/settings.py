"""从环境变量名读取连接配置，但绝不读取或打印 ``.env`` 文件内容。"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Settings:
    """外部服务的连接配置。

    无参数创建时会读取当前进程环境变量。数据库地址默认指向Windows回环地址，
    由SSH隧道转发到虚拟机回环端口；密码没有默认值，源码不会出现真实凭据。
    """

    vm_host: str
    es_url: str
    es_index: str
    exercise_index: str
    redis_host: str
    redis_port: int
    redis_db: int
    neo4j_uri: str
    neo4j_user: str
    neo4j_password: str | None
    cache_ttl_seconds: int
    data_version: str

    @classmethod
    def from_env(cls) -> Settings:
        """读取环境变量；未设置时使用无敏感信息的项目默认值。"""

        vm_host = os.getenv("VM_HOST", "192.168.220.77")
        service_host = os.getenv("DAY37_SERVICE_HOST", "127.0.0.1")
        return cls(
            vm_host=vm_host,
            es_url=os.getenv("ES_URL", f"http://{service_host}:19200"),
            es_index=os.getenv("ES_INDEX", "day37_bank_knowledge_v1"),
            exercise_index=os.getenv("ES_EXERCISE_INDEX", "day37_product_exercise_v1"),
            redis_host=os.getenv("REDIS_HOST", service_host),
            redis_port=int(os.getenv("REDIS_PORT", "6380")),
            redis_db=int(os.getenv("REDIS_DB", "0")),
            neo4j_uri=os.getenv("NEO4J_URI", f"bolt://{service_host}:7689"),
            neo4j_user=os.getenv("NEO4J_USER", "neo4j"),
            neo4j_password=os.getenv("NEO4J_PASSWORD"),
            cache_ttl_seconds=int(os.getenv("CACHE_TTL_SECONDS", "300")),
            data_version=os.getenv("DATA_VERSION", "v1"),
        )
