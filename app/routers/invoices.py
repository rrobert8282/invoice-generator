from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app import models, schemas
from app.services.pdf_service import render_invoice_pdf

router = APIRouter(tags=["invoices"])


# ---- internal helpers -------------------------------------------------

def get_invoice_or_404(invoice_id: str, db: Session) -> models.Invoice:
    invoice = (
        db.query(models.Invoice)
        .options(joinedload(models.Invoice.line_items), joinedload(models.Invoice.client))
        .filter(models.Invoice.id == invoice_id)
        .first()
    )
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return invoice


def get_line_item_or_404(line_item_id: str, db: Session) -> models.LineItem:
    line_item = db.query(models.LineItem).filter(models.LineItem.id == line_item_id).first()
    if line_item is None:
        raise HTTPException(status_code=404, detail="Line item not found")
    return line_item


def ensure_draft(invoice: models.Invoice):
    """Line items and most invoice fields are only editable while status is draft.
    Once an invoice is sent, it's treated as a frozen document -- see the
    architecture notes on why totals are stored rather than derived live."""
    if invoice.status != models.InvoiceStatus.draft:
        raise HTTPException(
            status_code=400,
            detail=f"Invoice is {invoice.status.value}; only draft invoices can be modified",
        )


def recompute_totals(invoice: models.Invoice):
    subtotal = sum((item.line_total for item in invoice.line_items), Decimal("0"))
    tax_amount = (subtotal * invoice.tax_rate / Decimal("100")).quantize(Decimal("0.01"))
    invoice.subtotal = subtotal
    invoice.tax_amount = tax_amount
    invoice.total = subtotal + tax_amount


def _is_overdue(invoice: models.Invoice) -> bool:
    """'Overdue' is deliberately not a stored status (see architecture notes) --
    it's a sent invoice whose due date has passed, computed at read time so it's
    never possible for the stored status and the real-world due date to drift
    out of sync with each other."""
    if invoice.status != models.InvoiceStatus.sent:
        return False
    due = invoice.due_date
    if due.tzinfo is None:  # SQLite doesn't reliably round-trip tzinfo; assume UTC
        due = due.replace(tzinfo=timezone.utc)
    return due < datetime.now(timezone.utc)


def serialize_invoice(invoice: models.Invoice) -> schemas.InvoiceOut:
    out = schemas.InvoiceOut.model_validate(invoice)
    if _is_overdue(invoice):
        out.status = "overdue"
    return out


def generate_invoice_number(db: Session) -> str:
    year = datetime.now(timezone.utc).year
    prefix = f"INV-{year}-"
    count = (
        db.query(models.Invoice)
        .filter(models.Invoice.invoice_number.like(f"{prefix}%"))
        .count()
    )
    return f"{prefix}{count + 1:04d}"


# ---- invoice endpoints --------------------------------------------------

@router.post("/invoices", response_model=schemas.InvoiceOut, status_code=201)
def create_invoice(payload: schemas.InvoiceCreate, db: Session = Depends(get_db)):
    client = db.query(models.Client).filter(models.Client.id == payload.client_id).first()
    if client is None:
        raise HTTPException(status_code=404, detail="Client not found")

    invoice = models.Invoice(
        invoice_number=generate_invoice_number(db),
        client_id=payload.client_id,
        issue_date=payload.issue_date,
        due_date=payload.due_date,
        tax_rate=payload.tax_rate,
        notes=payload.notes,
    )

    for item_payload in payload.line_items:
        line_total = (item_payload.quantity * item_payload.unit_price).quantize(Decimal("0.01"))
        invoice.line_items.append(
            models.LineItem(
                description=item_payload.description,
                quantity=item_payload.quantity,
                unit_price=item_payload.unit_price,
                line_total=line_total,
            )
        )

    recompute_totals(invoice)

    db.add(invoice)
    db.commit()
    db.refresh(invoice)
    return serialize_invoice(invoice)


VALID_STATUS_FILTERS = {"draft", "sent", "paid", "overdue"}


@router.get("/invoices", response_model=list[schemas.InvoiceOut])
def list_invoices(
    client_id: Optional[str] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
):
    if status is not None and status not in VALID_STATUS_FILTERS:
        raise HTTPException(
            status_code=400,
            detail=f"status must be one of {sorted(VALID_STATUS_FILTERS)}",
        )

    query = db.query(models.Invoice).options(joinedload(models.Invoice.line_items))
    if client_id is not None:
        query = query.filter(models.Invoice.client_id == client_id)

    invoices = query.order_by(models.Invoice.created_at.desc()).all()
    serialized = [serialize_invoice(inv) for inv in invoices]

    # Filtered in Python rather than SQL because "overdue" isn't a stored column --
    # it's the same computed view used by serialize_invoice elsewhere, so filtering
    # here stays guaranteed-consistent with what a single GET /invoices/{id} shows.
    if status is not None:
        serialized = [inv for inv in serialized if inv.status == status]

    return serialized


@router.get("/invoices/{invoice_id}", response_model=schemas.InvoiceOut)
def get_invoice(invoice_id: str, db: Session = Depends(get_db)):
    invoice = get_invoice_or_404(invoice_id, db)
    return serialize_invoice(invoice)


@router.patch("/invoices/{invoice_id}", response_model=schemas.InvoiceOut)
def update_invoice(invoice_id: str, payload: schemas.InvoiceUpdate, db: Session = Depends(get_db)):
    invoice = get_invoice_or_404(invoice_id, db)
    ensure_draft(invoice)

    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(invoice, field, value)

    if "tax_rate" in updates:
        recompute_totals(invoice)

    db.commit()
    db.refresh(invoice)
    return serialize_invoice(invoice)


@router.delete("/invoices/{invoice_id}", status_code=204)
def delete_invoice(invoice_id: str, db: Session = Depends(get_db)):
    invoice = get_invoice_or_404(invoice_id, db)
    ensure_draft(invoice)
    db.delete(invoice)
    db.commit()


# ---- line item endpoints -------------------------------------------------

@router.post("/invoices/{invoice_id}/line-items", response_model=schemas.InvoiceOut, status_code=201)
def add_line_item(invoice_id: str, payload: schemas.LineItemCreate, db: Session = Depends(get_db)):
    invoice = get_invoice_or_404(invoice_id, db)
    ensure_draft(invoice)

    line_total = (payload.quantity * payload.unit_price).quantize(Decimal("0.01"))
    invoice.line_items.append(
        models.LineItem(
            description=payload.description,
            quantity=payload.quantity,
            unit_price=payload.unit_price,
            line_total=line_total,
        )
    )
    recompute_totals(invoice)

    db.commit()
    db.refresh(invoice)
    return serialize_invoice(invoice)


@router.patch("/line-items/{line_item_id}", response_model=schemas.InvoiceOut)
def update_line_item(line_item_id: str, payload: schemas.LineItemUpdate, db: Session = Depends(get_db)):
    line_item = get_line_item_or_404(line_item_id, db)
    invoice = get_invoice_or_404(line_item.invoice_id, db)
    ensure_draft(invoice)

    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(line_item, field, value)
    line_item.line_total = (line_item.quantity * line_item.unit_price).quantize(Decimal("0.01"))

    recompute_totals(invoice)

    db.commit()
    db.refresh(invoice)
    return serialize_invoice(invoice)


@router.delete("/line-items/{line_item_id}", response_model=schemas.InvoiceOut)
def delete_line_item(line_item_id: str, db: Session = Depends(get_db)):
    line_item = get_line_item_or_404(line_item_id, db)
    invoice = get_invoice_or_404(line_item.invoice_id, db)
    ensure_draft(invoice)

    db.delete(line_item)
    db.flush()
    db.refresh(invoice)
    recompute_totals(invoice)

    db.commit()
    db.refresh(invoice)
    return serialize_invoice(invoice)


# ---- status transitions ---------------------------------------------------

@router.post("/invoices/{invoice_id}/send", response_model=schemas.InvoiceOut)
def send_invoice(invoice_id: str, db: Session = Depends(get_db)):
    invoice = get_invoice_or_404(invoice_id, db)
    if invoice.status != models.InvoiceStatus.draft:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot send an invoice that is {invoice.status.value}; only draft invoices can be sent",
        )
    if not invoice.line_items:
        raise HTTPException(status_code=400, detail="Cannot send an invoice with no line items")

    invoice.status = models.InvoiceStatus.sent
    invoice.sent_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(invoice)
    return serialize_invoice(invoice)


@router.post("/invoices/{invoice_id}/mark-paid", response_model=schemas.InvoiceOut)
def mark_invoice_paid(invoice_id: str, db: Session = Depends(get_db)):
    invoice = get_invoice_or_404(invoice_id, db)
    # Note: this also covers the "overdue" case -- overdue is a display-only view
    # over a sent invoice (see _is_overdue), so the real stored status here is
    # still `sent`, and marking it paid works exactly the same way.
    if invoice.status != models.InvoiceStatus.sent:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot mark paid an invoice that is {invoice.status.value}; it must be sent first",
        )

    invoice.status = models.InvoiceStatus.paid
    invoice.paid_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(invoice)
    return serialize_invoice(invoice)


# ---- PDF ---------------------------------------------------------------

@router.get("/invoices/{invoice_id}/pdf")
def get_invoice_pdf(invoice_id: str, db: Session = Depends(get_db)):
    invoice = get_invoice_or_404(invoice_id, db)
    pdf_bytes = render_invoice_pdf(invoice, invoice.client)
    filename = f"invoice-{invoice.invoice_number}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )