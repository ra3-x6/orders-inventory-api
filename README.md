# Orders and Inventory API

[![Python checks](https://github.com/ra3-x6/orders-inventory-api/actions/workflows/ci.yml/badge.svg)](https://github.com/ra3-x6/orders-inventory-api/actions/workflows/ci.yml)

A Python backend that reserves restaurant inventory, tracks order state, and exports line items for sales reporting. The demo uses synthetic orders and Egyptian pounds. Prices are stored as integer piastres.

| Capability | Behavior |
| --- | --- |
| Stock reservation | A conditional database update reserves each item only when enough stock is available. One transaction commits all order lines and stock changes together. |
| Safe retry | Send a unique `Idempotency-Key` with each new order. A replay of the same items returns the existing order without reserving more stock. Reusing the key with different items returns `409`. |
| Order lifecycle | New orders start pending. Completion keeps the reservation. Cancellation restores stock once. Both final states prevent further transitions. |
| Reporting | Export a UTF-8 CSV with one row per order line, including the price and product name captured when the order was placed. |

## Run locally

Python 3.11 or later is required. From this directory, run the following in PowerShell. The default stores demo data in `orders.db` with SQLite.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m uvicorn orders_api.main:app
```

On macOS or Linux, replace `.\.venv\Scripts\python.exe` with `.venv/bin/python`. Open [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) to try the endpoints. Use the same terminal syntax with `-m pytest -q` or `-m ruff check .` to run the checks.

### PostgreSQL with Docker

From this directory with Docker running:

```sh
docker compose up --build
```

Compose runs the API and PostgreSQL 16. The API port is bound to localhost. The development database starts with the included demo credentials and keeps its data in the Compose volume. To stop services, use `docker compose down`. Use a fresh database when checking the example totals. A database configured through `DATABASE_URL` receives the initial tables at startup.

To run the API tests against a separate PostgreSQL test database, set `TEST_DATABASE_URL` to a SQLAlchemy URL such as `postgresql+psycopg://orders:your-password@127.0.0.1:5432/orders_test`, then run pytest. The test user needs permission to create and drop test schemas in that database. Each test uses its own schema. CI is configured to exercise PostgreSQL and SQLite.

## Try the full flow

With the API running, open a second terminal in this project folder.

```sh
python examples/demo.py
```

The demo creates two completed orders and one cancelled order, checks that replaying each creation request returns the same order ID, then saves `output/orders.csv`. With a fresh database the completed orders total **EGP 400.00**. Each run creates new demo orders and the export includes all orders in the database.

The CSV can be passed directly to the companion [Sales Report Automation](https://github.com/ra3-x6/sales-report-automation#use-an-api-export) CLI. The export columns are `order_id,line_id,ordered_at,status,sku,product_name,quantity,unit_price_minor,currency`. `ordered_at` is an ISO 8601 UTC timestamp. The column contract is also included in the reporting repository.

## Endpoints

| Method and path | What it does |
| --- | --- |
| `GET /health` | Process health |
| `POST /products` | Create a product with opening stock |
| `GET /products` | List catalog items with pagination |
| `POST /products/{sku}/restock` | Add stock |
| `POST /orders` | Create an order and reserve stock |
| `GET /orders/{order_id}` | Retrieve an order with line items |
| `PATCH /orders/{order_id}/status` | Complete or cancel an order |
| `GET /orders/export.csv` | Export order lines for reporting |

Example product body

```json
{"sku": "TEA", "name": "Iced Tea", "unit_price_minor": 2500, "stock": 6}
```

Example order body. Set the request header `Idempotency-Key` to `demo-order-001` in the interactive docs.

```json
{"items": [{"sku": "TEA", "quantity": 2}]}
```

## Design notes

- The order record claims the retry key before stock is touched. Stock updates process SKUs in a stable order. If a line cannot be filled, the transaction rolls back the earlier reservations and the key claim.
- The status update only changes a pending order. Returning to the same final state is a no-op. Cancellation and stock restoration share the same transaction.
- This demo targets local use with a small dataset. A public deployment would need authentication, managed migrations, and bounded exports.

Tests exercise competing requests for the last unit, concurrent replays, rollback of a partially fillable order, the cancellation rule, and the CSV contract.
