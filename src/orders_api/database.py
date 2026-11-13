"""Database schema and engine configuration."""

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    create_engine,
    event,
)
from sqlalchemy.engine import Engine

metadata = MetaData()

products = Table(
    "products",
    metadata,
    Column("sku", String(64), primary_key=True),
    Column("name", String(120), nullable=False),
    Column("unit_price_minor", Integer, nullable=False),
    Column("stock", Integer, nullable=False),
    CheckConstraint("unit_price_minor BETWEEN 0 AND 100000000"),
    CheckConstraint("stock BETWEEN 0 AND 1000000"),
)

orders = Table(
    "orders",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("request_key", String(100), nullable=False, unique=True),
    Column("request_hash", String(64), nullable=False),
    Column("ordered_at", DateTime(timezone=True), nullable=False, index=True),
    Column("status", String(12), nullable=False),
    Column("total_minor", BigInteger, nullable=False),
    CheckConstraint("status IN ('pending', 'completed', 'cancelled')"),
    CheckConstraint("total_minor >= 0"),
)

order_lines = Table(
    "order_lines",
    metadata,
    Column("order_id", ForeignKey("orders.id"), primary_key=True),
    Column("line_id", Integer, primary_key=True),
    Column("sku", ForeignKey("products.sku"), nullable=False),
    Column("product_name", String(120), nullable=False),
    Column("quantity", Integer, nullable=False),
    Column("unit_price_minor", Integer, nullable=False),
    CheckConstraint("quantity BETWEEN 1 AND 10000"),
    CheckConstraint("unit_price_minor BETWEEN 0 AND 100000000"),
)


def make_engine(database_url: str) -> Engine:
    engine = create_engine(database_url, pool_pre_ping=True)
    if engine.dialect.name == "sqlite":

        @event.listens_for(engine, "connect")
        def enable_foreign_keys(dbapi_connection, _connection_record) -> None:
            dbapi_connection.execute("PRAGMA foreign_keys = ON")

    return engine
