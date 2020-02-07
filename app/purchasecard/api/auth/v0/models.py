from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel

from app.commons.api.models import PaymentResponse


class StoreInfo(BaseModel):
    store_id: str
    store_city: str
    store_business_name: str


class CreateAuthRequest(BaseModel):
    subtotal: int
    subtotal_tax: int
    store_meta: StoreInfo
    delivery_id: str
    shift_id: str
    ttl: Optional[int]
    external_user_token: str


class CreateAuthResponse(PaymentResponse):
    delivery_id: str
    created_at: datetime
    updated_at: datetime


class UpdateAuthRequest(BaseModel):
    subtotal: int
    subtotal_tax: int
    store_meta: StoreInfo
    delivery_id: str
    delivery_requires_purchase_card: bool
    shift_id: str
    ttl: Optional[int]


class UpdateAuthResponse(PaymentResponse):
    delivery_id: str
    updated_at: datetime
    state: str


class CloseAuthRequest(BaseModel):
    delivery_id: str
    shift_id: str


class CloseAuthResponse(BaseModel):
    state: str


class CloseAllAuthRequest(BaseModel):
    shift_id: str


class CloseAllAuthResponse(BaseModel):
    states: List[str]
    num_success: int
