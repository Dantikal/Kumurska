# app/modules/loyalty/schemas.py
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel


class LoyaltyLevelRead(BaseModel):
    id: UUID
    name: str
    cashback_percent: Decimal
    threshold: Decimal
    effective_from: datetime
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class BonusAccountRead(BaseModel):
    id: UUID
    user_id: UUID
    level_id: UUID
    level_name: str
    cashback_percent: Decimal
    balance: int
    accumulated_total: Decimal
    level_expires_at: datetime | None
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class BonusTransactionRead(BaseModel):
    id: UUID
    account_id: UUID
    purchase_id: UUID | None
    type: str
    amount: int
    reason: str | None
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}
