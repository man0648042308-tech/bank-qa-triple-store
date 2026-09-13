from __future__ import annotations

from day37_bank_qa.answer_generator import OptionalLLMAnswerGenerator
from day37_bank_qa.cache import InMemoryTTLCache
from day37_bank_qa.elasticsearch_retriever import FixtureTextRetriever
from day37_bank_qa.main import build_parser
from day37_bank_qa.models import Customer
from day37_bank_qa.neo4j_repository import FixtureGraphRetriever
from day37_bank_qa.pipeline import BankQAPipeline, CustomerNotFoundError, build_offline_pipeline


def test_cli_accepts_explicit_offline_and_defaults_to_offline() -> None:
    parser = build_parser()

    default_args = parser.parse_args([])
    explicit_args = parser.parse_args(["--offline"])

    assert default_args.online is False
    assert explicit_args.offline is True
    assert explicit_args.online is False


def test_offline_pipeline_applies_hard_rules_and_then_hits_cache() -> None:
    pipeline = build_offline_pipeline()

    first = pipeline.ask("C001", "请推荐稳健产品")
    second = pipeline.ask("C001", "请推荐稳健产品")

    assert first.cache_hit is False
    assert second.cache_hit is True
    assert first.recommended_product_ids == ("P001",)
    assert "P002" not in first.recommended_product_ids  # C001是R1，不能推荐R2。
    assert "P003" not in first.recommended_product_ids
    assert "P005" not in first.recommended_product_ids
    assert first.sources


def test_same_question_for_different_customers_never_reuses_answer() -> None:
    pipeline = build_offline_pipeline()

    first_customer = pipeline.ask("C001", "推荐产品")
    second_customer = pipeline.ask("C002", "推荐产品")

    assert first_customer.cache_hit is False
    assert second_customer.cache_hit is False
    assert first_customer.customer_id != second_customer.customer_id
    assert first_customer.recommended_product_ids != second_customer.recommended_product_ids


def test_langchain_runnable_invokes_same_pipeline() -> None:
    runnable = build_offline_pipeline().as_runnable()

    answer = runnable.invoke({"customer_id": "C002", "question": "推荐理财", "top_k": 2})

    assert answer.customer_id == "C002"
    assert set(answer.recommended_product_ids).issubset({"P001", "P002"})


def test_missing_customer_is_an_explicit_business_error() -> None:
    pipeline = build_offline_pipeline()

    try:
        pipeline.ask("C404", "推荐产品")
    except CustomerNotFoundError as exc:
        assert "C404" in str(exc)
    else:
        raise AssertionError("不存在的客户必须抛出 CustomerNotFoundError")


def test_out_of_scope_question_is_refused_without_products_or_sources() -> None:
    answer = build_offline_pipeline().ask("C001", "今天天气怎么样")

    assert "不属于银行产品问答范围" in answer.text
    assert answer.recommended_product_ids == ()
    assert answer.sources == ()


def test_non_bank_recommendation_word_does_not_bypass_domain_gate() -> None:
    answer = build_offline_pipeline().ask("C001", "请推荐一道晚餐菜谱")

    assert "不属于银行产品问答范围" in answer.text
    assert answer.recommended_product_ids == ()


def test_product_fact_answer_is_not_misrepresented_as_recommendation() -> None:
    answer = build_offline_pipeline().ask("C001", "安心存款起投金额是多少？")

    assert "安心存款（P001）" in answer.text
    assert "起投金额1000元" in answer.text
    assert "产品事实" in answer.text
    assert answer.recommended_product_ids == ()
    assert any("P001" in source for source in answer.sources)


class MutableCustomerRepository:
    def __init__(self) -> None:
        self.customer = Customer("C001", "张三", "R1", 5_000)

    def get_customer(self, customer_id: str) -> Customer | None:
        return self.customer if customer_id == self.customer.customer_id else None


def test_changed_customer_profile_cannot_reuse_old_cached_recommendation() -> None:
    repository = MutableCustomerRepository()
    pipeline = BankQAPipeline(
        customer_repository=repository,
        text_retriever=FixtureTextRetriever(),
        graph_retriever=FixtureGraphRetriever(),
        cache=InMemoryTTLCache(),
    )

    first = pipeline.ask("C001", "推荐产品")
    repository.customer = Customer("C001", "张三", "R3", 5_000)
    second = pipeline.ask("C001", "推荐产品")

    assert first.cache_hit is False
    assert second.cache_hit is False
    assert first.recommended_product_ids == ("P001",)
    assert "P002" in second.recommended_product_ids


class FakeModel:
    def __init__(self) -> None:
        self.prompt = ""

    def invoke(self, input: str) -> str:
        self.prompt = input
        return "基于给定证据，P001可供参考。"


def test_optional_llm_only_receives_already_filtered_evidence() -> None:
    model = FakeModel()
    pipeline = build_offline_pipeline()
    pipeline._answer_generator = OptionalLLMAnswerGenerator(model)  # noqa: SLF001

    answer = pipeline.ask("C001", "推荐产品")

    assert answer.text == "基于给定证据，P001可供参考。"
    assert "P001" in model.prompt
    assert "成长基金" not in model.prompt
    assert answer.recommended_product_ids == ("P001",)


class UnsafeFakeModel:
    def invoke(self, input: str) -> str:
        del input
        return "P999保证收益，绝对安全。"


def test_optional_llm_unsafe_text_falls_back_to_deterministic_answer() -> None:
    pipeline = build_offline_pipeline()
    pipeline._answer_generator = OptionalLLMAnswerGenerator(UnsafeFakeModel())  # noqa: SLF001

    answer = pipeline.ask("C001", "推荐产品")

    assert "P999" not in answer.text
    assert "保证收益" not in answer.text
    assert "课程演示" in answer.text
