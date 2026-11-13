import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.schema import CreateSchema, DropSchema

from orders_api.main import create_app


@pytest.fixture
def client(tmp_path):
    postgres_url = os.getenv("TEST_DATABASE_URL")
    if not postgres_url:
        with TestClient(create_app(f"sqlite+pysqlite:///{tmp_path / 'orders.db'}")) as test_client:
            yield test_client
        return

    # Each test has its own schema, including tests that use several connections.
    schema = f"test_{uuid4().hex}"
    admin = create_engine(postgres_url)
    url = make_url(postgres_url).update_query_dict({"options": f"-csearch_path={schema}"})
    try:
        with admin.begin() as db:
            db.execute(CreateSchema(schema))
        with TestClient(create_app(url.render_as_string(hide_password=False))) as test_client:
            yield test_client
    finally:
        with admin.begin() as db:
            db.execute(DropSchema(schema, cascade=True, if_exists=True))
        admin.dispose()
