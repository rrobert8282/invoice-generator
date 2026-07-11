from decimal import Decimal
from typing import List
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, ConfigDict, Field


class ClientBase(BaseModel):
    name: str
    email: EmailStr
    phone: Optional[str] = None
    address: Optional[str] = None


class ClientCreate(ClientBase):
    pass


class ClientUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    address: Optional[str] = None


class ClientOut(ClientBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime


class LineItemCreate(BaseModel):
    description: str
    quantity: Decimal
    unit_price: Decimal


class LineItemUpdate(BaseModel):
    description: Optional[str] = None
    quantity: Optional[Decimal] = None
    unit_price: Optional[Decimal] = None


class LineItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    description: str
    quantity: Decimal
    unit_price: Decimal
    line_total: Decimal


class InvoiceCreate(BaseModel):
    client_id: str
    issue_date: datetime
    due_date: datetime
    tax_rate: Decimal = Decimal("0")
    notes: Optional[str] = None
    line_items: List[LineItemCreate] = Field(default_factory=list)


class InvoiceUpdate(BaseModel):
    # Deliberately excludes client_id and status -- client reassignment and status
    # transitions are separate concerns (status transitions land in Phase 3).
    issue_date: Optional[datetime] = None
    due_date: Optional[datetime] = None
    tax_rate: Optional[Decimal] = None
    notes: Optional[str] = None


class InvoiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    invoice_number: str
    client_id: str
    status: str
    issue_date: datetime
    due_date: datetime
    sent_at: Optional[datetime] = None
    paid_at: Optional[datetime] = None
    tax_rate: Decimal
    notes: Optional[str] = None
    subtotal: Decimal
    tax_amount: Decimal
    total: Decimal
    created_at: datetime
    updated_at: datetime
    line_items: List[LineItemOut] = []