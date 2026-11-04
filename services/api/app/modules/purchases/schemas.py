# app/modules/purchases/schemas.py
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel


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
