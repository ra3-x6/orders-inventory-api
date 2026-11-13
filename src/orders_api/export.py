"""CSV contract shared with Sales Report Automation."""

import csv
from io import StringIO

from sqlalchemy import Engine, select

from .database import order_lines, orders
from .service import as_utc

COLUMNS = (
    "order_id",
    "line_id",
    "ordered_at",
    "status",
    "sku",
    "product_name",
    "quantity",
    "unit_price_minor",
    "currency",
)


def export_csv(engine: Engine) -> str:
    output = StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(COLUMNS)
    statement = (
        select(
            orders.c.id,
            order_lines.c.line_id,
            orders.c.ordered_at,
            orders.c.status,
            order_lines.c.sku,
            order_lines.c.product_name,
            order_lines.c.quantity,
            order_lines.c.unit_price_minor,
        )
        .join(order_lines, order_lines.c.order_id == orders.c.id)
        .order_by(orders.c.ordered_at, orders.c.id, order_lines.c.line_id)
    )
    with engine.connect() as db:
        for row in db.execute(statement):
            writer.writerow(
                (
                    row.id,
                    row.line_id,
                    as_utc(row.ordered_at).isoformat(),
                    row.status,
                    row.sku,
                    row.product_name,
                    row.quantity,
                    row.unit_price_minor,
                    "EGP",
                )
            )
    return output.getvalue()
