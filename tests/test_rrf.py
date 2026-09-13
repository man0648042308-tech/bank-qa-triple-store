from __future__ import annotations

import pytest

from day37_bank_qa.models import RetrievalHit
from day37_bank_qa.rrf import reciprocal_rank_fusion


def make_hit(item_id: str, source: str) -> RetrievalHit:
    return RetrievalHit(item_id, item_id, "内容", 99.0, source, item_id)


def test_shared_candidate_wins_and_sources_are_combined() -> None:
    result = reciprocal_rank_fusion(
        {
            "elasticsearch": [make_hit("P001", "es"), make_hit("P002", "es")],
            "neo4j": [make_hit("P002", "graph"), make_hit("P003", "graph")],
        },
        k=60,
        top_k=3,
    )

    assert [hit.source_id for hit in result] == ["P002", "P001", "P003"]
    assert result[0].source == "elasticsearch+neo4j"
    assert result[0].score == pytest.approx(1 / 62 + 1 / 61)


def test_duplicate_in_one_group_is_only_counted_once_and_ties_use_id() -> None:
    result = reciprocal_rank_fusion(
        {"es": [make_hit("P002", "es"), make_hit("P002", "es"), make_hit("P001", "es")]},
        k=0,
        top_k=10,
    )

    assert [hit.source_id for hit in result] == ["P002", "P001"]
    assert result[0].score == pytest.approx(1.0)


def test_rrf_boundary_validation() -> None:
    assert reciprocal_rank_fusion({}, top_k=0) == []
    with pytest.raises(ValueError):
        reciprocal_rank_fusion({}, k=-1)

