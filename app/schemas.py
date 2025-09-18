from pydantic import BaseModel, Field
from typing import Optional

class PurchaseIn(BaseModel):
    eventId: str
    qty: int = Field(gt=0, le=10)

class PurchaseOut(BaseModel):
    orderId: Optional[str] = None
    status: str
    remaining: int
    holdExpiresAt: Optional[str] = None
    reason: Optional[str] = None

class PayOut(BaseModel):
    ok: bool
    status: str
