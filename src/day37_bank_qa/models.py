"""项目中的核心数据模型。

初学者先把“数据模型”理解成统一的数据表格：所有模块都按同一种字段名称交换数据，
这样 Elasticsearch、Neo4j、Redis 和业务规则之间就不会因为字段含义不同而混乱。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class Customer:
    """银行客户画像。

    ``frozen=True`` 表示对象创建后不可直接改字段，避免推荐过程中误改客户资产；
    ``slots=True`` 会限制可用属性，拼错属性名时可以更早暴露错误。
    """

    customer_id: str
    name: str
    risk_level: str
    available_amount: int


@dataclass(frozen=True, slots=True)
class Product:
    """可被检索、过滤和推荐的银行产品。"""

    product_id: str
    name: str
    category: str
    risk_level: str
    min_investment: int
    status: str
    description: str


@dataclass(frozen=True, slots=True)
class RetrievalHit:
    """某个检索器返回的一条候选证据。

    ``source_id`` 是去重键；``source`` 说明证据来自 ES 还是 Neo4j；
    ``product_id`` 允许业务规则找到对应产品；``metadata`` 保存扩展字段。
    """

    source_id: str
    title: str
    content: str
    score: float
    source: str
    product_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Answer:
    """问答流水线最终返回的结构化结果。"""

    question: str
    customer_id: str
    text: str
    sources: tuple[str, ...]
    recommended_product_ids: tuple[str, ...]
    cache_hit: bool = False

    def to_dict(self) -> dict[str, Any]:
        """把对象转换成可被 JSON 和 FastAPI 使用的普通字典。"""

        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Answer:
        """从缓存中的普通字典恢复 ``Answer`` 对象。"""

        return cls(
            question=str(data["question"]),
            customer_id=str(data["customer_id"]),
            text=str(data["text"]),
            sources=tuple(data.get("sources", ())),
            recommended_product_ids=tuple(data.get("recommended_product_ids", ())),
            cache_hit=bool(data.get("cache_hit", False)),
        )

