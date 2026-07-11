import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Numeric, ForeignKey, DateTime, Enum, Text
from sqlalchemy.orm import relationship

from app.database import Base


def gen_uuid():
    return str(uuid.uuid4())


class InvoiceStatus(str, enum.Enum):
    draft = "draft"
    sent = "sent"
    paid = "paid"


class Client(Base):
    __tablename__ = "clients"

    id = Column(String, primary_key=True, default=gen_uuid)
    name = Column(String, nullable=False)
    email = Column(String, nullable=False)
    phone = Column(String, nullable=True)
    address = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    invoices = relationship("Invoice", back_populates="client", cascade="all, delete-orphan")


class Invoice(Base):
    __tablename__ = "invoices"

    id = Column(String, primary_key=True, default=gen_uuid)
    invoice_number = Column(String, unique=True, nullable=False)
    client_id = Column(String, ForeignKey("clients.id"), nullable=False)
    status = Column(Enum(InvoiceStatus), default=InvoiceStatus.draft, nullable=False)

    issue_date = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    due_date = Column(DateTime(timezone=True), nullable=False)
    sent_at = Column(DateTime(timezone=True), nullable=True)
    paid_at = Column(DateTime(timezone=True), nullable=True)

    tax_rate = Column(Numeric(5, 2), default=0)
    notes = Column(Text, nullable=True)

    # Stored (not derived) totals -- frozen once the invoice leaves draft status.
    subtotal = Column(Numeric(10, 2), default=0)
    tax_amount = Column(Numeric(10, 2), default=0)
    total = Column(Numeric(10, 2), default=0)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    client = relationship("Client", back_populates="invoices")
    line_items = relationship("LineItem", back_populates="invoice", cascade="all, delete-orphan")


class LineItem(Base):
    __tablename__ = "line_items"

    id = Column(String, primary_key=True, default=gen_uuid)
    invoice_id = Column(String, ForeignKey("invoices.id"), nullable=False)
    description = Column(String, nullable=False)
    quantity = Column(Numeric(10, 2), nullable=False)
    unit_price = Column(Numeric(10, 2), nullable=False)
    line_total = Column(Numeric(10, 2), nullable=False)

    invoice = relationship("Invoice", back_populates="line_items")