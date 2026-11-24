# app/modules/purchases/schemas.py
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


class PurchaseItemCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    quantity: int = Field(gt=0)
    unit_price: Decimal = Field(ge=0)
    line_total: Decimal = Field(ge=0)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Название товара не может быть пустым")
        return value


class PurchaseCreate(BaseModel):
    source: str = Field(min_length=1, max_length=50)
    external_id: str = Field(min_length=1, max_length=100)
    user_id: UUID
    items: list[PurchaseItemCreate] = Field(min_length=1)
    total_amount: Decimal = Field(ge=0)
    paid_amount: Decimal = Field(ge=0)
    purchased_at: datetime
    receipt_number: str | None = Field(default=None, max_length=100)
    points_redeemed: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_amounts(self):
        if self.paid_amount > self.total_amount:
            raise ValueError("Оплаченная сумма не может превышать общую сумму")
        return self


class PurchaseItemRead(BaseModel):
    id: UUID
    purchase_id: UUID
    name: str
    quantity: int
    unit_price: Decimal
    line_total: Decimal

    model_config = {"from_attributes": True}


class PurchaseRead(BaseModel):
    id: UUID
    receipt_number: str | None
    total_amount: Decimal
    paid_amount: Decimal
    points_redeemed: int
    cashback_earned: int
    purchased_at: datetime
    status: str
    items: list[PurchaseItemRead]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
