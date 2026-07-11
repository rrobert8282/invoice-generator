"""
Seeds the database with demo data: one demo user, a few clients, and invoices
covering every status (draft, sent, paid, and an overdue sent invoice) -- so a
fresh deployment has something to look at instead of an empty database.

Run with: docker compose exec api python scripts/seed.py

Safe to run more than once -- it checks for existing demo data first and skips
seeding if the demo user already has clients, rather than creating duplicates.
"""
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone
from decimal import Decimal

# Makes this runnable as `python scripts/seed.py` from any working directory,
# not just when the project root happens to already be on sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import SessionLocal, Base, engine
from app import models
from app.auth import hash_password
from app.routers.invoices import recompute_totals, generate_invoice_number

DEMO_EMAIL = "demo@example.com"
DEMO_PASSWORD = "demopassword123"


def get_or_create_demo_user(db):
    user = db.query(models.User).filter(models.User.email == DEMO_EMAIL).first()
    if user:
        print(f"Demo user already exists: {DEMO_EMAIL}")
        return user
    user = models.User(email=DEMO_EMAIL, hashed_password=hash_password(DEMO_PASSWORD))
    db.add(user)
    db.commit()
    db.refresh(user)
    print(f"Created demo user: {DEMO_EMAIL} / {DEMO_PASSWORD}")
    return user


def create_client(db, user, name, email, phone=None, address=None):
    client = models.Client(user_id=user.id, name=name, email=email, phone=phone, address=address)
    db.add(client)
    db.commit()
    db.refresh(client)
    return client


def create_invoice(db, user, client, status, due_date, line_items,
                    tax_rate=Decimal("0"), notes=None, sent_at=None, paid_at=None):
    invoice = models.Invoice(
        user_id=user.id,
        client_id=client.id,
        invoice_number=generate_invoice_number(db),
        status=status,
        issue_date=datetime.now(timezone.utc) - timedelta(days=20),
        due_date=due_date,
        tax_rate=tax_rate,
        notes=notes,
        sent_at=sent_at,
        paid_at=paid_at,
    )
    for desc, qty, price in line_items:
        line_total = (Decimal(qty) * Decimal(price)).quantize(Decimal("0.01"))
        invoice.line_items.append(models.LineItem(
            description=desc, quantity=Decimal(qty), unit_price=Decimal(price), line_total=line_total
        ))
    recompute_totals(invoice)
    db.add(invoice)
    db.commit()
    db.refresh(invoice)
    return invoice


def main():
    Base.metadata.create_all(bind=engine)  # safety net if run before the app's own startup
    db = SessionLocal()
    try:
        user = get_or_create_demo_user(db)

        existing_clients = db.query(models.Client).filter(models.Client.user_id == user.id).count()
        if existing_clients > 0:
            print(f"Demo user already has {existing_clients} client(s) -- skipping to avoid duplicates.")
            print("Delete the demo user's data first if you want to reseed.")
            return

        now = datetime.now(timezone.utc)

        acme = create_client(db, user, "Acme Studios", "billing@acmestudios.com",
                              "555-0101", "123 Design Ave, Austin, TX")
        globex = create_client(db, user, "Globex Corp", "ap@globex.com",
                                "555-0102", "500 Corporate Pkwy, Denver, CO")
        initech = create_client(db, user, "Initech LLC", "finance@initech.com")

        # Draft -- not yet sent
        create_invoice(
            db, user, acme, models.InvoiceStatus.draft,
            due_date=now + timedelta(days=14),
            line_items=[("Landing page redesign", "1", "1200.00"), ("Copywriting", "3", "150.00")],
            notes="Draft -- pending final scope confirmation.",
        )

        # Sent, not yet due
        create_invoice(
            db, user, globex, models.InvoiceStatus.sent,
            due_date=now + timedelta(days=10),
            line_items=[("Backend API development", "40", "75.00"), ("Code review & QA", "8", "60.00")],
            tax_rate=Decimal("8.25"),
            notes="Net 14 payment terms.",
            sent_at=now - timedelta(days=4),
        )

        # Sent and overdue -- due_date in the past, so the API will display this as "overdue"
        create_invoice(
            db, user, initech, models.InvoiceStatus.sent,
            due_date=now - timedelta(days=6),
            line_items=[("Monthly retainer -- June", "1", "2000.00")],
            sent_at=now - timedelta(days=20),
            notes="Second reminder sent.",
        )

        # Paid
        create_invoice(
            db, user, acme, models.InvoiceStatus.paid,
            due_date=now - timedelta(days=25),
            line_items=[("Brand identity package", "1", "3500.00")],
            sent_at=now - timedelta(days=35),
            paid_at=now - timedelta(days=28),
        )

        print("\nSeed complete:")
        print(f"  Login: {DEMO_EMAIL} / {DEMO_PASSWORD}")
        print("  Clients: 3 (Acme Studios, Globex Corp, Initech LLC)")
        print("  Invoices: 4 (draft, sent, sent+overdue, paid)")
    finally:
        db.close()


if __name__ == "__main__":
    main()