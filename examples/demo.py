"""Create example orders through the API and download a sales export."""

import argparse
import json
from pathlib import Path
from urllib.request import Request, urlopen
from uuid import uuid4


def request(base_url, method, path, body=None, headers=None):
    request_headers = dict(headers or {})
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        request_headers["Content-Type"] = "application/json"
    with urlopen(
        Request(base_url + path, data=data, method=method, headers=request_headers), timeout=10
    ) as response:
        return response.read()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--output", type=Path, default=Path("output/orders.csv"))
    args = parser.parse_args()
    base_url = args.url.rstrip("/")
    token = uuid4().hex[:8].upper()
    burger, fries = f"BURGER-{token}", f"FRIES-{token}"

    for sku, name, price in ((burger, "House Burger", 12_000), (fries, "Fries", 4_000)):
        request(
            base_url,
            "POST",
            "/products",
            {
                "sku": sku,
                "name": name,
                "unit_price_minor": price,
                "stock": 10,
            },
        )

    for number, (status, items) in enumerate(
        (
            ("completed", [(burger, 2), (fries, 1)]),
            ("completed", [(burger, 1)]),
            ("cancelled", [(fries, 1)]),
        ),
        1,
    ):
        payload = {"items": [{"sku": sku, "quantity": quantity} for sku, quantity in items]}
        headers = {"Idempotency-Key": f"demo-{token}-{number}"}
        order = json.loads(request(base_url, "POST", "/orders", payload, headers))
        replay = json.loads(request(base_url, "POST", "/orders", payload, headers))
        assert replay["id"] == order["id"]
        request(base_url, "PATCH", f"/orders/{order['id']}/status", {"status": status})
        print(f"{status:9} {order['id']} | {order['total_minor'] / 100:.2f} EGP")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(request(base_url, "GET", "/orders/export.csv"))
    print(f"Exported orders to {args.output}")


if __name__ == "__main__":
    main()
