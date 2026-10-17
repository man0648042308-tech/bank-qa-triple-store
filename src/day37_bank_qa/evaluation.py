"""离线Evaluation Harness：用固定案例验证推荐、事实问答和拒答边界。"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from .pipeline import build_offline_pipeline


@dataclass(frozen=True, slots=True)
class EvaluationCase:
    """一条预先定义的输入和硬成功标准。"""

    name: str
    customer_id: str
    question: str
    expected_product_ids: tuple[str, ...]
    required_text: tuple[str, ...]
    expect_sources: bool


EVALUATION_CASES = (
    EvaluationCase(
        "低风险推荐只保留P001",
        "C001",
        "请推荐适合低风险客户的稳健产品",
        ("P001",),
        ("风险等级为R1", "功能演示"),
        True,
    ),
    EvaluationCase(
        "无关天气问题必须拒答",
        "C001",
        "今天天气怎么样",
        (),
        ("不属于银行产品问答范围",),
        False,
    ),
    EvaluationCase(
        "起投金额是事实而不是推荐",
        "C001",
        "安心存款起投金额是多少？",
        (),
        ("P001", "起投金额1000元", "产品事实"),
        True,
    ),
    EvaluationCase(
        "高风险产品事实可以查询但不能误标推荐",
        "C001",
        "成长基金的风险等级是什么？",
        (),
        ("P003", "风险等级R4", "产品事实"),
        True,
    ),
)


def run_offline_evaluation() -> dict[str, object]:
    """执行固定评估集，返回可保存为JSON的结构化成功/失败证据。"""

    results: list[dict[str, object]] = []
    for case in EVALUATION_CASES:
        answer = build_offline_pipeline().ask(case.customer_id, case.question)
        failures: list[str] = []
        if answer.recommended_product_ids != case.expected_product_ids:
            failures.append(
                f"expected_ids={case.expected_product_ids}, "
                f"actual_ids={answer.recommended_product_ids}"
            )
        missing_text = [text for text in case.required_text if text not in answer.text]
        if missing_text:
            failures.append(f"missing_text={missing_text}")
        if bool(answer.sources) is not case.expect_sources:
            failures.append(
                f"expected_sources={case.expect_sources}, actual_sources={answer.sources}"
            )
        results.append(
            {
                "case": asdict(case),
                "passed": not failures,
                "failures": failures,
                "actual": answer.to_dict(),
            }
        )

    passed = sum(1 for result in results if result["passed"])
    total = len(results)
    return {
        "suite": "day37_offline_bank_qa_v1",
        "pass_threshold": 1.0,
        "passed": passed,
        "total": total,
        "score": passed / total,
        "results": results,
    }


def main() -> None:
    """打印UTF-8 JSON；任一硬案例失败时以非零状态结束。"""

    report = run_offline_evaluation()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["score"] < report["pass_threshold"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
