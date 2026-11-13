import csv
from concurrent.futures import ThreadPoolExecutor
from io import StringIO
from threading import Barrier


def add_product(client, sku="TEA", stock=3, price=1250):
    response = client.post(
        "/products",
        json={
            "sku": sku,
            "name": f"{sku} item",
            "stock": stock,
            "unit_price_minor": price,
        },
    )
    assert response.status_code == 201, response.text


def place_order(client, key, *items):
    return client.post(
        "/orders",
        headers={"Idempotency-Key": key},
        json={"items": [{"sku": sku, "quantity": quantity} for sku, quantity in items]},
    )


def stocks(client):
    return {product["sku"]: product["stock"] for product in client.get("/products").json()}


def test_order_retry_uses_same_id_and_reserves_stock_once(client):
    add_product(client)
    add_product(client, "FRIES")
    first = place_order(client, "request-1", ("TEA", 2), ("FRIES", 1))
    repeated = place_order(client, "request-1", ("FRIES", 1), ("TEA", 2))
    assert first.status_code == 201
    assert repeated.status_code == 200
    assert repeated.json() == first.json()
    assert first.json()["total_minor"] == 3750
    assert stocks(client) == {"FRIES": 2, "TEA": 1}
    assert place_order(client, "request-1", ("TEA", 1)).status_code == 409


def test_insufficient_stock_rolls_back_all_reservations_and_request_key(client):
    add_product(client, "A-TEA", stock=5)
    add_product(client, "B-SIDE", stock=0)
    response = place_order(client, "rollback", ("A-TEA", 2), ("B-SIDE", 1))
    assert response.status_code == 409
    assert stocks(client) == {"A-TEA": 5, "B-SIDE": 0}
    assert list(csv.DictReader(StringIO(client.get("/orders/export.csv").text))) == []
    assert client.post("/products/B-SIDE/restock", json={"quantity": 2}).status_code == 200
    assert place_order(client, "rollback", ("A-TEA", 2), ("B-SIDE", 1)).status_code == 201


def test_cancel_releases_stock_once_and_cannot_be_completed(client):
    add_product(client)
    order = place_order(client, "cancel", ("TEA", 2)).json()
    endpoint = f"/orders/{order['id']}/status"
    for _ in range(2):
        assert client.patch(endpoint, json={"status": "cancelled"}).status_code == 200
    assert client.patch(endpoint, json={"status": "completed"}).status_code == 409
    assert stocks(client) == {"TEA": 3}


def test_competing_orders_cannot_oversell_last_unit(client):
    add_product(client, stock=1)
    gate = Barrier(2)

    def send(key):
        gate.wait(timeout=5)
        return place_order(client, key, ("TEA", 1))

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(send, ("first", "second")))
    assert sorted(response.status_code for response in results) == [201, 409]
    assert stocks(client) == {"TEA": 0}


def test_concurrent_retry_same_key_creates_one_order(client):
    add_product(client, stock=2)
    gate = Barrier(2)

    def send(_):
        gate.wait(timeout=5)
        return place_order(client, "same-key", ("TEA", 1))

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(send, range(2)))
    assert sorted(response.status_code for response in results) == [200, 201]
    assert results[0].json()["id"] == results[1].json()["id"]
    assert stocks(client) == {"TEA": 1}


def test_export_uses_order_snapshot_schema(client):
    add_product(client)
    order = place_order(client, "export", ("TEA", 2)).json()
    status = client.patch(f"/orders/{order['id']}/status", json={"status": "completed"})
    assert status.status_code == 200
    response = client.get("/orders/export.csv")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    rows = list(csv.DictReader(StringIO(response.text)))
    assert len(rows) == 1
    row = rows[0]
    assert row == {
        "order_id": order["id"],
        "line_id": "1",
        "ordered_at": row["ordered_at"],
        "status": "completed",
        "sku": "TEA",
        "product_name": "TEA item",
        "quantity": "2",
        "unit_price_minor": "1250",
        "currency": "EGP",
    }
    assert row["ordered_at"].endswith("+00:00")


def test_invalid_payload_and_missing_idempotency_key(client):
    add_product(client)
    assert (
        client.post("/orders", json={"items": [{"sku": "TEA", "quantity": 1}]}).status_code == 422
    )
    assert place_order(client, "duplicates", ("TEA", 1), ("TEA", 1)).status_code == 422
    assert place_order(client, "zero", ("TEA", 0)).status_code == 422
    assert stocks(client) == {"TEA": 3}


def test_completed_order_keeps_its_reservation(client):
    add_product(client)
    order = place_order(client, "complete", ("TEA", 2)).json()
    endpoint = f"/orders/{order['id']}/status"
    assert client.patch(endpoint, json={"status": "completed"}).status_code == 200
    assert client.patch(endpoint, json={"status": "cancelled"}).status_code == 409
    assert stocks(client) == {"TEA": 1}
