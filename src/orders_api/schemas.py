"""Request validation and public response shapes."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

SKU = Annotated[str, StringConstraints(pattern=r"^[A-Z0-9][A-Z0-9_.-]{0,63}$")]
Price = Annotated[int, Field(strict=True, ge=0, le=100_000_000)]
Stock = Annotated[int, Field(strict=True, ge=0, le=1_000_000)]
Quantity = Annotated[int, Field(strict=True, ge=1, le=10_000)]
OrderStatus = Literal["pending", "completed", "cancelled"]


class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProductCreate(RequestModel):
    sku: SKU
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
    unit_price_minor: Price
    stock: Stock

    @field_validator("name")
    @classmethod
    def reject_control_characters(cls, name: str) -> str:
        if any(ord(character) < 32 for character in name):
            raise ValueError("Name contains a control character")
        return name


class Product(ProductCreate):
    currency: Literal["EGP"] = "EGP"


class Restock(RequestModel):
    quantity: Quantity


class OrderItem(RequestModel):
    sku: SKU
    quantity: Quantity


class OrderCreate(RequestModel):
    items: Annotated[list[OrderItem], Field(min_length=1, max_length=30)]

    @field_validator("items")
    @classmethod
    def reject_duplicate_skus(cls, items: list[OrderItem]) -> list[OrderItem]:
        if len({item.sku for item in items}) != len(items):
            raise ValueError("Each SKU may appear only once per order")
        return items


class StatusUpdate(RequestModel):
    status: Literal["completed", "cancelled"]


class OrderLine(BaseModel):
    line_id: int
    sku: str
    product_name: str
    quantity: int
    unit_price_minor: int


class Order(BaseModel):
    id: str
    ordered_at: datetime
    status: OrderStatus
    total_minor: int
    currency: Literal["EGP"] = "EGP"
    items: list[OrderLine]
