"""用 Reciprocal Rank Fusion（倒数排名融合）合并多个检索列表。"""

from __future__ import annotations

from dataclasses import replace

from .models import RetrievalHit


def reciprocal_rank_fusion(
    ranked_groups: dict[str, list[RetrievalHit]],
    *,
    k: int = 60,
    top_k: int = 10,
) -> list[RetrievalHit]:
    """按 ``1 / (k + rank)`` 累加同一候选在各列表中的排名分数。

    ES的BM25分数和图查询分数并不处于同一量纲，不能直接相加；RRF只比较各自列表
    内的名次。``rank`` 从1开始，因此列表第一名贡献 ``1/(k+1)``。
    """

    if k < 0:
        raise ValueError("k 不能小于 0")
    if top_k <= 0:
        return []

    scores: dict[str, float] = {}
    representative: dict[str, RetrievalHit] = {}
    sources: dict[str, set[str]] = {}

    for group_name, hits in ranked_groups.items():
        seen_in_group: set[str] = set()
        for rank, hit in enumerate(hits, start=1):
            # 同一检索器重复返回同一ID时，只计算第一次，防止人为刷高分数。
            if hit.source_id in seen_in_group:
                continue
            seen_in_group.add(hit.source_id)
            scores[hit.source_id] = scores.get(hit.source_id, 0.0) + 1.0 / (k + rank)
            representative.setdefault(hit.source_id, hit)
            sources.setdefault(hit.source_id, set()).add(group_name or hit.source)

    ordered_ids = sorted(scores, key=lambda item_id: (-scores[item_id], item_id))
    return [
        replace(
            representative[item_id],
            score=scores[item_id],
            source="+".join(sorted(sources[item_id])),
        )
        for item_id in ordered_ids[:top_k]
    ]

