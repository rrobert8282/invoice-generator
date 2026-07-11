# Invoice Generator

A backend API for freelancers and small businesses to manage clients and generate
professional PDF invoices. Built with FastAPI, SQLAlchemy, PostgreSQL, and WeasyPrint.

![Sample invoice PDF](docs/sample-invoice.png)

## Features

- Client management (CRUD)
- Invoice management with nested line items, computed subtotal/tax/total
- Status lifecycle: `draft → sent → paid`, with a computed `overdue` view
  (a sent invoice past its due date — not a separate stored state)
- Draft-lock enforcement: once an invoice is sent, it's treated as a frozen
  document — line items and invoice fields can no longer be edited
- Professional PDF generation (`GET /invoices/{id}/pdf`) via WeasyPrint
- Filtering invoices by client and status
- Dockerized end-to-end — same image runs locally and in production

## Tech stack

- **API**: FastAPI + SQLAlchemy
- **DB**: PostgreSQL (Neon in production, containerized Postgres for local dev)
- **PDF**: WeasyPrint (HTML/CSS → PDF) + Jinja2 templates
- **Migrations**: Alembic
- **Tests**: pytest, 41 tests covering CRUD, totals math, status transitions,
  draft-lock enforcement, filtering, and PDF generation

## Running locally

Requires Docker Desktop.

```bash
docker compose up --build
```

This starts the API on `http://localhost:8000` and a Postgres container. First
build takes a few minutes (installing WeasyPrint's system dependencies).

Run the test suite:
```bash
docker compose exec api pytest tests/ -v
```

## API overview

| Method | Endpoint | Description |
|---|---|---|
| POST | `/clients` | Create a client |
| GET | `/clients` | List clients |
| GET | `/clients/{id}` | Get a client |
| PATCH | `/clients/{id}` | Update a client |
| DELETE | `/clients/{id}` | Delete a client |
| POST | `/invoices` | Create an invoice (with nested line items) |
| GET | `/invoices?client_id=&status=` | List/filter invoices |
| GET | `/invoices/{id}` | Get an invoice |
| PATCH | `/invoices/{id}` | Update an invoice (draft only) |
| DELETE | `/invoices/{id}` | Delete an invoice (draft only) |
| POST | `/invoices/{id}/send` | draft → sent |
| POST | `/invoices/{id}/mark-paid` | sent → paid |
| POST | `/invoices/{id}/line-items` | Add a line item (draft only) |
| PATCH | `/line-items/{id}` | Update a line item (draft only) |
| DELETE | `/line-items/{id}` | Delete a line item (draft only) |
| GET | `/invoices/{id}/pdf` | Download the invoice as a PDF |

## Known gaps

- **No authentication yet.** Every endpoint is currently open. JWT auth
  (reusing the pattern from an earlier project) is planned before this is
  deployed anywhere public — not yet implemented.
- **No email delivery.** PDFs are generated on demand, not sent automatically.
- **Invoice numbers aren't gap-proof.** They're derived by counting existing
  invoices per year, so a deleted invoice can leave a gap in the sequence.

## Future work

- Stripe payment links on invoices, so clients can pay directly from the PDF
  or a hosted invoice page
- Email delivery of invoices (SendGrid/SES)
- Recurring/subscription invoices
- Multi-currency support
- Partial payments / payment history per invoice
- Cron-based auto-flip to `overdue` (currently computed at read time instead)
- Customizable branding per business (logo, colors)