"""FastAPI routes and application lifecycle."""

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID

from fastapi import FastAPI, Header, Query, Request, Response
from fastapi.responses import JSONResponse

from . import service
from .database import make_engine, metadata
from .export import export_csv
from .schemas import SKU, Order, OrderCreate, Product, ProductCreate, Restock, StatusUpdate


def create_app(database_url: str | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        url = database_url or os.getenv("DATABASE_URL", "sqlite+pysqlite:///orders.db")
        engine = make_engine(url)
        try:
            metadata.create_all(engine)
            app.state.engine = engine
            yield
        finally:
            engine.dispose()

    app = FastAPI(
        title="Orders and Inventory API",
        description="Reserve stock, manage order states and export order lines for reporting.",
        version="1.0.0",
        lifespan=lifespan,
    )

    @app.exception_handler(service.OrderError)
    async def order_error(_request: Request, exc: service.OrderError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"detail": str(exc)})

    @app.get("/health", tags=["Health"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/products", tags=["Products"], status_code=201)
    def add_product(payload: ProductCreate) -> Product:
        return service.add_product(app.state.engine, payload)

    @app.get("/products", tags=["Products"])
    def list_products(
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> list[Product]:
        return service.list_products(app.state.engine, limit, offset)

    @app.post("/products/{sku}/restock", tags=["Products"])
    def restock(sku: SKU, payload: Restock) -> Product:
        return service.restock(app.state.engine, sku, payload.quantity)

    @app.post(
        "/orders",
        tags=["Orders"],
        status_code=201,
        responses={200: {"model": Order, "description": "Existing order returned"}},
    )
    def create_order(
        payload: OrderCreate,
        response: Response,
        key: Annotated[str, Header(alias="Idempotency-Key", pattern=r"^[!-~]{1,100}$")],
    ) -> Order:
        order, created = service.create_order(app.state.engine, payload, key)
        if not created:
            response.status_code = 200
        return order

    @app.get("/orders/export.csv", tags=["Orders"], response_class=Response)
    def download_orders() -> Response:
        return Response(
            export_csv(app.state.engine),
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="orders.csv"'},
        )

    @app.get("/orders/{order_id}", tags=["Orders"])
    def get_order(order_id: UUID) -> Order:
        return service.get_order(app.state.engine, str(order_id))

    @app.patch("/orders/{order_id}/status", tags=["Orders"])
    def update_status(order_id: UUID, payload: StatusUpdate) -> Order:
        return service.update_status(app.state.engine, str(order_id), payload.status)

    return app


app = create_app()
