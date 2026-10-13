"""FastAPI接口：健康检查、产品搜索和银行问答。"""

from __future__ import annotations

import os
from hmac import compare_digest
from typing import Protocol

from fastapi import Depends, FastAPI, HTTPException, Query, Security
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field

from exercise05.search_products import ProductSearchHit, ProductSearchResponse

from .pipeline import BankQAPipeline, CustomerNotFoundError, build_offline_pipeline
from .sample_data import PRODUCTS


class ProductSearchService(Protocol):
    """产品搜索端点依赖的最小接口。"""

    def search_products(
        self,
        *,
        keyword: str | None = None,
        min_price: float | None = None,
        max_price: float | None = None,
        category: str | None = None,
    ) -> ProductSearchResponse: ...


class AskRequest(BaseModel):
    """``POST /qa/ask`` 的JSON请求体。"""

    customer_id: str = Field(min_length=1, max_length=32, examples=["C001"])
    question: str = Field(
        min_length=1,
        max_length=500,
        examples=["我有5000元，可以选择什么稳健产品？"],
    )
    top_k: int = Field(default=5, ge=1, le=10)


class OfflineProductSearch:
    """离线搜索实现，用固定产品证明API无需数据库也可以启动。"""

    def search_products(
        self,
        *,
        keyword: str | None = None,
        min_price: float | None = None,
        max_price: float | None = None,
        category: str | None = None,
    ) -> ProductSearchResponse:
        cleaned_keyword = (keyword or "").strip()
        cleaned_category = (category or "").strip()
        if min_price is not None and max_price is not None and min_price > max_price:
            raise ValueError("min_price 不能大于 max_price")
        items: list[ProductSearchHit] = []
        for product in PRODUCTS:
            if cleaned_keyword and cleaned_keyword not in product.name:
                continue
            if cleaned_category and product.category != cleaned_category:
                continue
            if min_price is not None and product.min_investment < min_price:
                continue
            if max_price is not None and product.min_investment > max_price:
                continue
            highlighted_name = (
                product.name.replace(cleaned_keyword, f"<em>{cleaned_keyword}</em>")
                if cleaned_keyword
                else product.name
            )
            items.append(
                ProductSearchHit(
                    # 离线API复用银行产品ID（如P001），练习五真实ES则使用整数ID。
                    # ``ProductSearchHit`` 严格遵守练习五整数合同，所以这里取数字部分。
                    product_id=int(product.product_id.removeprefix("P")),
                    name=product.name,
                    highlighted_name=highlighted_name,
                    category=product.category,
                    price=float(product.min_investment),
                    stock=0,
                    score=1.0 if cleaned_keyword else 0.0,
                )
            )
        return ProductSearchResponse(total=len(items), items=tuple(items[:10]))


def create_app(
    *,
    pipeline: BankQAPipeline | None = None,
    product_search: ProductSearchService | None = None,
    mode: str = "offline",
    api_key: str | None = None,
) -> FastAPI:
    """创建应用；业务端点统一要求环境注入的 ``X-API-Key``。"""

    selected_pipeline = pipeline or build_offline_pipeline()
    selected_search = product_search or OfflineProductSearch()
    configured_api_key = api_key if api_key is not None else os.getenv("DAY37_API_KEY")
    api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

    def require_api_key(provided_key: str | None = Security(api_key_header)) -> None:
        """缺失/错误凭据返回401；服务端未配置则返回503并拒绝泄露业务数据。"""

        if not configured_api_key:
            raise HTTPException(status_code=503, detail="服务端尚未配置 DAY37_API_KEY")
        if provided_key is None or not compare_digest(provided_key, configured_api_key):
            raise HTTPException(
                status_code=401,
                detail="缺少或错误的 X-API-Key",
                headers={"WWW-Authenticate": "ApiKey"},
            )

    application = FastAPI(
        title="Day37 银行智能问答系统",
        version="0.2.0",
        dependencies=[Depends(require_api_key)],
    )

    @application.get("/health")
    def health() -> dict[str, str]:
        """只表示Web应用进程可响应；真实数据库由独立验证脚本检查。"""

        return {"status": "ok", "mode": mode}

    @application.get("/products/search")
    def products_search(
        keyword: str | None = Query(default=None, max_length=100),
        min_price: float | None = Query(default=None, ge=0),
        max_price: float | None = Query(default=None, ge=0),
        category: str | None = Query(default=None, max_length=100),
    ) -> ProductSearchResponse:
        try:
            return selected_search.search_products(
                keyword=keyword,
                min_price=min_price,
                max_price=max_price,
                category=category,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @application.post("/qa/ask")
    def ask(request: AskRequest) -> dict[str, object]:
        try:
            answer = selected_pipeline.ask(
                customer_id=request.customer_id,
                question=request.question,
                top_k=request.top_k,
            )
        except CustomerNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return answer.to_dict()

    return application


def _build_default_app() -> FastAPI:
    """模块导入时默认离线；仅显式设置 ``DAY37_MODE=online`` 才连接真实服务。"""

    mode = os.getenv("DAY37_MODE", "offline").strip().casefold()
    if mode != "online":
        return create_app(mode="offline")

    # 延迟导入避免离线学习时不必要地创建外部客户端。
    from exercise05.search_products import ElasticsearchProductSearch

    from .main import build_online_pipeline, build_service_clients
    from .settings import Settings

    settings = Settings.from_env()
    clients = build_service_clients(settings)
    pipeline = build_online_pipeline(settings, clients=clients)
    product_search = ElasticsearchProductSearch(clients.es, settings.exercise_index)
    return create_app(pipeline=pipeline, product_search=product_search, mode="online")


app = _build_default_app()


