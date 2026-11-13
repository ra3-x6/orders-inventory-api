"""Order and stock operations. Each mutation owns one database transaction."""

import hashlib
import json
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import Connection, Engine, insert, select, update
from sqlalchemy.exc import IntegrityError

from .database import order_lines, orders, products
from .schemas import Order, OrderCreate, OrderStatus, Product, ProductCreate


class OrderError(Exception):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code


def add_product(engine: Engine, request: ProductCreate) -> Product:
    try:
        with engine.begin() as db:
            row = (
                db.execute(insert(products).values(**request.model_dump()).returning(products))
                .mappings()
                .one()
            )
            return Product.model_validate(dict(row))
    except IntegrityError:
        with engine.connect() as db:
            exists = db.scalar(select(products.c.sku).where(products.c.sku == request.sku))
        if exists is None:
            raise
        raise OrderError(409, f"SKU already exists: {request.sku}") from None


def list_products(engine: Engine, limit: int, offset: int) -> list[Product]:
    with engine.connect() as db:
        rows = db.execute(
            select(products).order_by(products.c.sku).limit(limit).offset(offset)
        ).mappings()
        return [Product.model_validate(dict(row)) for row in rows]


def restock(engine: Engine, sku: str, quantity: int) -> Product:
    with engine.begin() as db:
        row = (
            db.execute(
                update(products)
                .where(products.c.sku == sku, products.c.stock <= 1_000_000 - quantity)
                .values(stock=products.c.stock + quantity)
                .returning(products)
            )
            .mappings()
            .one_or_none()
        )
        if row is not None:
            return Product.model_validate(dict(row))
        if db.scalar(select(products.c.sku).where(products.c.sku == sku)) is None:
            raise OrderError(404, f"Unknown SKU: {sku}")
        raise OrderError(409, f"Stock limit exceeded for {sku}")


def fetch_order(db: Connection, order_id: str) -> Order:
    row = db.execute(select(orders).where(orders.c.id == order_id)).mappings().one_or_none()
    if row is None:
        raise OrderError(404, "Order not found")
    items = db.execute(
        select(order_lines)
        .where(order_lines.c.order_id == order_id)
        .order_by(order_lines.c.line_id)
    ).mappings()
    return Order(
        id=row["id"],
        ordered_at=as_utc(row["ordered_at"]),
        status=row["status"],
        total_minor=row["total_minor"],
        items=[dict(item) for item in items],
    )


def get_order(engine: Engine, order_id: str) -> Order:
    with engine.connect() as db:
        return fetch_order(db, order_id)


def as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def create_order(engine: Engine, request: OrderCreate, key: str) -> tuple[Order, bool]:
    items = sorted(request.items, key=lambda item: item.sku)
    canonical = json.dumps([(item.sku, item.quantity) for item in items], separators=(",", ":"))
    fingerprint = hashlib.sha256(canonical.encode()).hexdigest()
    order_id = str(uuid4())
    try:
        with engine.begin() as db:
            # Claim the key before touching inventory. A failed order rolls the claim back.
            db.execute(
                insert(orders).values(
                    id=order_id,
                    request_key=key,
                    request_hash=fingerprint,
                    ordered_at=datetime.now(UTC),
                    status="pending",
                    total_minor=0,
                )
            )
            lines = []
            for index, item in enumerate(items, 1):
                product = (
                    db.execute(
                        update(products)
                        .where(products.c.sku == item.sku, products.c.stock >= item.quantity)
                        .values(stock=products.c.stock - item.quantity)
                        .returning(products.c.name, products.c.unit_price_minor)
                    )
                    .mappings()
                    .one_or_none()
                )
                if product is None:
                    if db.scalar(select(products.c.sku).where(products.c.sku == item.sku)) is None:
                        raise OrderError(404, f"Unknown SKU: {item.sku}")
                    raise OrderError(409, f"Insufficient stock for {item.sku}")
                lines.append(
                    {
                        "order_id": order_id,
                        "line_id": index,
                        "sku": item.sku,
                        "product_name": product["name"],
                        "quantity": item.quantity,
                        "unit_price_minor": product["unit_price_minor"],
                    }
                )
            db.execute(insert(order_lines), lines)
            total = sum(line["quantity"] * line["unit_price_minor"] for line in lines)
            db.execute(update(orders).where(orders.c.id == order_id).values(total_minor=total))
            return fetch_order(db, order_id), True
    except IntegrityError:
        # A concurrent attempt can commit this key while our insert is waiting.
        with engine.connect() as db:
            original = db.execute(
                select(orders.c.id, orders.c.request_hash).where(orders.c.request_key == key)
            ).one_or_none()
            if original is None:
                raise
            if original.request_hash != fingerprint:
                raise OrderError(409, "Idempotency-Key belongs to a different request") from None
            return fetch_order(db, original.id), False


def update_status(engine: Engine, order_id: str, target: OrderStatus) -> Order:
    with engine.begin() as db:
        changed = db.scalar(
            update(orders)
            .where(orders.c.id == order_id, orders.c.status == "pending")
            .values(status=target)
            .returning(orders.c.id)
        )
        order = fetch_order(db, order_id)
        if changed is None and order.status != target:
            raise OrderError(409, f"Cannot change a {order.status} order to {target}")
        if changed is not None and target == "cancelled":
            for item in sorted(order.items, key=lambda line: line.sku):
                restored = db.scalar(
                    update(products)
                    .where(
                        products.c.sku == item.sku,
                        products.c.stock <= 1_000_000 - item.quantity,
                    )
                    .values(stock=products.c.stock + item.quantity)
                    .returning(products.c.sku)
                )
                if restored is None:
                    raise OrderError(409, f"Restoring stock would exceed the limit for {item.sku}")
        return order
