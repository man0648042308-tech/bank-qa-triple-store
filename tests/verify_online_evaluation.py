"""将既有4条固定问答合同用于真实三库；不改动评估标准。"""

from __future__ import annotations

import json

from day37_bank_qa.evaluation import EVALUATION_CASES
from day37_bank_qa.main import build_online_pipeline, build_service_clients
from day37_bank_qa.settings import Settings


def main() -> None:
    settings = Settings.from_env()
    clients = build_service_clients(settings)
    try:
        pipeline = build_online_pipeline(settings, clients=clients)
        results = []
        for case in EVALUATION_CASES:
            answer = pipeline.ask(case.customer_id, case.question)
            checks = {
                "ids": answer.recommended_product_ids == case.expected_product_ids,
                "text": all(text in answer.text for text in case.required_text),
                "sources": bool(answer.sources) is case.expect_sources,
            }
            results.append({
                "case": case.name,
                "passed": all(checks.values()),
                "failures": [name for name, passed in checks.items() if not passed],
                "actual": answer.to_dict(),
            })
        print(json.dumps(results, ensure_ascii=False, indent=2))
        if not all(result["passed"] for result in results):
            raise SystemExit(1)
        print(f"ONLINE_EVALUATION_PASS cases={len(results)}")
    finally:
        clients.neo4j.close()  # type: ignore[attr-defined]
        clients.es.close()
        clients.redis.close()


if __name__ == "__main__":
    main()
