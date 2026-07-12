from datetime import datetime, timedelta, timezone


def make_client(client, name="Test Client", email="client@example.com"):
    return client.post("/clients", json={"name": name, "email": email}).json()


def invoice_payload(client_id, tax_rate="0", line_items=None, due_date=None):
    now = datetime.now(timezone.utc)
    return {
        "client_id": client_id,
        "issue_date": now.isoformat(),
        "due_date": (due_date or (now + timedelta(days=14))).isoformat(),
        "tax_rate": tax_rate,
        "line_items": line_items or [],
    }


def test_create_invoice_computes_totals(client):
    c = make_client(client)
    payload = invoice_payload(
        c["id"],
        tax_rate="10",
        line_items=[
            {"description": "Design work", "quantity": "5", "unit_price": "100.00"},
            {"description": "Hosting", "quantity": "1", "unit_price": "20.00"},
        ],
    )
    response = client.post("/invoices", json=payload)
    assert response.status_code == 201
    body = response.json()

    assert body["status"] == "draft"
    assert body["invoice_number"].startswith("INV-")
    assert len(body["line_items"]) == 2
    assert body["subtotal"] == "520.00"   # (5*100) + (1*20)
    assert body["tax_amount"] == "52.00"  # 10% of 520
    assert body["total"] == "572.00"


def test_invoice_number_increments(client):
    c = make_client(client)
    first = client.post("/invoices", json=invoice_payload(c["id"])).json()
    second = client.post("/invoices", json=invoice_payload(c["id"])).json()
    assert first["invoice_number"] != second["invoice_number"]


def test_create_invoice_unknown_client_404(client):
    response = client.post("/invoices", json=invoice_payload("does-not-exist"))
    assert response.status_code == 404


def test_add_line_item_recomputes_totals(client):
    c = make_client(client)
    invoice = client.post("/invoices", json=invoice_payload(c["id"])).json()

    response = client.post(
        f"/invoices/{invoice['id']}/line-items",
        json={"description": "Extra hours", "quantity": "2", "unit_price": "50.00"},
    )
    assert response.status_code == 201
    body = response.json()
    assert len(body["line_items"]) == 1
    assert body["subtotal"] == "100.00"
    assert body["total"] == "100.00"


def test_update_line_item_recomputes_totals(client):
    c = make_client(client)
    invoice = client.post(
        "/invoices",
        json=invoice_payload(c["id"], line_items=[{"description": "Work", "quantity": "1", "unit_price": "100.00"}]),
    ).json()
    line_item_id = invoice["line_items"][0]["id"]

    response = client.patch(f"/line-items/{line_item_id}", json={"quantity": "3"})
    assert response.status_code == 200
    body = response.json()
    assert body["subtotal"] == "300.00"


def test_delete_line_item_recomputes_totals(client):
    c = make_client(client)
    invoice = client.post(
        "/invoices",
        json=invoice_payload(
            c["id"],
            line_items=[
                {"description": "A", "quantity": "1", "unit_price": "50.00"},
                {"description": "B", "quantity": "1", "unit_price": "30.00"},
            ],
        ),
    ).json()
    line_item_id = invoice["line_items"][0]["id"]

    response = client.delete(f"/line-items/{line_item_id}")
    assert response.status_code == 200
    body = response.json()
    assert len(body["line_items"]) == 1
    assert body["subtotal"] == "30.00"


def test_draft_invoice_line_items_are_editable(client):
    # Full draft-lock enforcement (editing blocked once status leaves draft) gets
    # tested properly in Phase 3, once /send exists and can actually flip status.
    # This just confirms the baseline: a draft invoice's line items are editable.
    c = make_client(client)
    invoice = client.post(
        "/invoices",
        json=invoice_payload(c["id"], line_items=[{"description": "Work", "quantity": "1", "unit_price": "100.00"}]),
    ).json()

    line_item_id = invoice["line_items"][0]["id"]
    response = client.patch(f"/line-items/{line_item_id}", json={"quantity": "2"})
    assert response.status_code == 200


def test_delete_draft_invoice(client):
    c = make_client(client)
    invoice = client.post("/invoices", json=invoice_payload(c["id"])).json()
    response = client.delete(f"/invoices/{invoice['id']}")
    assert response.status_code == 204
    assert client.get(f"/invoices/{invoice['id']}").status_code == 404


def test_get_invoice_404(client):
    response = client.get("/invoices/does-not-exist")
    assert response.status_code == 404


def test_update_invoice_tax_rate_recomputes_total(client):
    c = make_client(client)
    invoice = client.post(
        "/invoices",
        json=invoice_payload(c["id"], line_items=[{"description": "Work", "quantity": "1", "unit_price": "200.00"}]),
    ).json()

    response = client.patch(f"/invoices/{invoice['id']}", json={"tax_rate": "5"})
    assert response.status_code == 200
    body = response.json()
    assert body["tax_amount"] == "10.00"
    assert body["total"] == "210.00"


def test_cannot_edit_line_item_once_not_draft(client, db_session):
    from app import models

    c = make_client(client)
    invoice = client.post(
        "/invoices",
        json=invoice_payload(c["id"], line_items=[{"description": "Work", "quantity": "1", "unit_price": "100.00"}]),
    ).json()
    line_item_id = invoice["line_items"][0]["id"]

    # Flip status directly at the DB level to simulate what Phase 3's /send will do.
    db_row = db_session.query(models.Invoice).filter(models.Invoice.id == invoice["id"]).first()
    db_row.status = models.InvoiceStatus.sent
    db_session.commit()

    response = client.patch(f"/line-items/{line_item_id}", json={"quantity": "2"})
    assert response.status_code == 400


def test_cannot_delete_line_item_once_not_draft(client, db_session):
    from app import models

    c = make_client(client)
    invoice = client.post(
        "/invoices",
        json=invoice_payload(c["id"], line_items=[{"description": "Work", "quantity": "1", "unit_price": "100.00"}]),
    ).json()
    line_item_id = invoice["line_items"][0]["id"]

    db_row = db_session.query(models.Invoice).filter(models.Invoice.id == invoice["id"]).first()
    db_row.status = models.InvoiceStatus.sent
    db_session.commit()

    response = client.delete(f"/line-items/{line_item_id}")
    assert response.status_code == 400


def test_cannot_delete_invoice_once_not_draft(client, db_session):
    from app import models

    c = make_client(client)
    invoice = client.post("/invoices", json=invoice_payload(c["id"])).json()

    db_row = db_session.query(models.Invoice).filter(models.Invoice.id == invoice["id"]).first()
    db_row.status = models.InvoiceStatus.sent
    db_session.commit()

    response = client.delete(f"/invoices/{invoice['id']}")
    assert response.status_code == 400


def test_cannot_update_invoice_once_not_draft(client, db_session):
    from app import models

    c = make_client(client)
    invoice = client.post("/invoices", json=invoice_payload(c["id"])).json()

    db_row = db_session.query(models.Invoice).filter(models.Invoice.id == invoice["id"]).first()
    db_row.status = models.InvoiceStatus.sent
    db_session.commit()

    response = client.patch(f"/invoices/{invoice['id']}", json={"notes": "changed"})
    assert response.status_code == 400


# ---- Phase 3: status transitions -------------------------------------------

def draft_invoice_with_item(client, **kwargs):
    c = make_client(client)
    return client.post(
        "/invoices",
        json=invoice_payload(c["id"], line_items=[{"description": "Work", "quantity": "1", "unit_price": "100.00"}], **kwargs),
    ).json()


def test_send_invoice_sets_status_and_timestamp(client):
    invoice = draft_invoice_with_item(client)
    response = client.post(f"/invoices/{invoice['id']}/send")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "sent"
    assert body["sent_at"] is not None


def test_cannot_send_invoice_with_no_line_items(client):
    c = make_client(client)
    invoice = client.post("/invoices", json=invoice_payload(c["id"])).json()
    response = client.post(f"/invoices/{invoice['id']}/send")
    assert response.status_code == 400


def test_cannot_send_already_sent_invoice(client):
    invoice = draft_invoice_with_item(client)
    client.post(f"/invoices/{invoice['id']}/send")
    response = client.post(f"/invoices/{invoice['id']}/send")
    assert response.status_code == 400


def test_cannot_mark_paid_before_sending(client):
    invoice = draft_invoice_with_item(client)
    response = client.post(f"/invoices/{invoice['id']}/mark-paid")
    assert response.status_code == 400


def test_mark_paid_after_send_sets_status_and_timestamp(client):
    invoice = draft_invoice_with_item(client)
    client.post(f"/invoices/{invoice['id']}/send")
    response = client.post(f"/invoices/{invoice['id']}/mark-paid")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "paid"
    assert body["paid_at"] is not None


def test_cannot_mark_paid_twice(client):
    invoice = draft_invoice_with_item(client)
    client.post(f"/invoices/{invoice['id']}/send")
    client.post(f"/invoices/{invoice['id']}/mark-paid")
    response = client.post(f"/invoices/{invoice['id']}/mark-paid")
    assert response.status_code == 400


def test_sent_invoice_past_due_date_shows_overdue(client):
    past_due = datetime.now(timezone.utc) - timedelta(days=5)
    invoice = draft_invoice_with_item(client, due_date=past_due)
    client.post(f"/invoices/{invoice['id']}/send")

    response = client.get(f"/invoices/{invoice['id']}")
    assert response.status_code == 200
    assert response.json()["status"] == "overdue"


def test_overdue_invoice_can_still_be_marked_paid(client):
    past_due = datetime.now(timezone.utc) - timedelta(days=5)
    invoice = draft_invoice_with_item(client, due_date=past_due)
    client.post(f"/invoices/{invoice['id']}/send")

    response = client.post(f"/invoices/{invoice['id']}/mark-paid")
    assert response.status_code == 200
    assert response.json()["status"] == "paid"


def test_draft_invoice_with_future_due_date_is_not_overdue(client):
    invoice = draft_invoice_with_item(client)  # default due_date is +14 days
    response = client.get(f"/invoices/{invoice['id']}")
    assert response.json()["status"] == "draft"


# ---- Phase 4: filtering/listing ---------------------------------------------

def test_filter_invoices_by_client_id(client):
    c1 = make_client(client, name="Client One", email="one@example.com")
    c2 = make_client(client, name="Client Two", email="two@example.com")
    client.post("/invoices", json=invoice_payload(c1["id"]))
    client.post("/invoices", json=invoice_payload(c1["id"]))
    client.post("/invoices", json=invoice_payload(c2["id"]))

    response = client.get(f"/invoices?client_id={c1['id']}")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert all(inv["client_id"] == c1["id"] for inv in body)


def test_filter_invoices_by_status(client):
    c = make_client(client)
    draft = client.post("/invoices", json=invoice_payload(c["id"])).json()
    sent = draft_invoice_with_item(client)
    client.post(f"/invoices/{sent['id']}/send")

    response = client.get("/invoices?status=draft")
    assert response.status_code == 200
    body = response.json()
    assert any(inv["id"] == draft["id"] for inv in body)
    assert all(inv["status"] == "draft" for inv in body)

    response = client.get("/invoices?status=sent")
    body = response.json()
    assert any(inv["id"] == sent["id"] for inv in body)
    assert all(inv["status"] == "sent" for inv in body)


def test_filter_invoices_by_status_overdue(client):
    past_due = datetime.now(timezone.utc) - timedelta(days=5)
    overdue_invoice = draft_invoice_with_item(client, due_date=past_due)
    client.post(f"/invoices/{overdue_invoice['id']}/send")

    not_overdue = draft_invoice_with_item(client)
    client.post(f"/invoices/{not_overdue['id']}/send")

    response = client.get("/invoices?status=overdue")
    assert response.status_code == 200
    body = response.json()
    ids = [inv["id"] for inv in body]
    assert overdue_invoice["id"] in ids
    assert not_overdue["id"] not in ids


def test_filter_invoices_by_client_and_status_combined(client):
    c1 = make_client(client, name="Client One", email="one@example.com")
    c2 = make_client(client, name="Client Two", email="two@example.com")
    client.post("/invoices", json=invoice_payload(c1["id"]))  # draft, c1
    client.post("/invoices", json=invoice_payload(c2["id"]))  # draft, c2

    response = client.get(f"/invoices?client_id={c1['id']}&status=draft")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["client_id"] == c1["id"]


def test_filter_invoices_invalid_status_rejected(client):
    response = client.get("/invoices?status=not-a-real-status")
    assert response.status_code == 400


# ---- Phase 5: PDF generation -------------------------------------------

def _extract_pdf_text(pdf_bytes: bytes) -> str:
    from io import BytesIO
    from pypdf import PdfReader

    reader = PdfReader(BytesIO(pdf_bytes))
    return "".join(page.extract_text() for page in reader.pages)


def test_pdf_generation_returns_valid_pdf(client):
    invoice = draft_invoice_with_item(client)
    response = client.get(f"/invoices/{invoice['id']}/pdf")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF-")
    # A real rendered invoice is comfortably several KB -- a near-empty/broken
    # render (e.g. an empty template) produces a "valid" PDF under ~1KB, which
    # a weaker ">500 bytes" check would silently let through undetected.
    assert len(response.content) > 3000


def test_pdf_contains_actual_invoice_content(client):
    # This is the test that would have caught the empty-template bug: it
    # doesn't just check the PDF is well-formed, it extracts the real text
    # and confirms the data we sent in is actually visible on the page.
    c = make_client(client, name="Distinctive Client Name", email="distinctive@example.com")
    invoice = client.post(
        "/invoices",
        json=invoice_payload(
            c["id"],
            line_items=[{"description": "Uniquely Named Consulting Work", "quantity": "1", "unit_price": "999.00"}],
        ),
    ).json()

    response = client.get(f"/invoices/{invoice['id']}/pdf")
    assert response.status_code == 200
    text = _extract_pdf_text(response.content)

    assert "Distinctive Client Name" in text
    assert "Uniquely Named Consulting Work" in text
    assert invoice["invoice_number"] in text
    assert "999.00" in text


def test_pdf_has_download_filename(client):
    invoice = draft_invoice_with_item(client)
    response = client.get(f"/invoices/{invoice['id']}/pdf")
    assert invoice["invoice_number"] in response.headers["content-disposition"]


def test_pdf_generation_multiple_line_items(client):
    c = make_client(client)
    invoice = client.post(
        "/invoices",
        json=invoice_payload(
            c["id"],
            tax_rate="8.5",
            line_items=[
                {"description": "Design", "quantity": "10", "unit_price": "75.00"},
                {"description": "Development", "quantity": "20", "unit_price": "90.00"},
                {"description": "QA", "quantity": "5", "unit_price": "60.00"},
            ],
        ),
    ).json()
    response = client.get(f"/invoices/{invoice['id']}/pdf")
    assert response.status_code == 200
    text = _extract_pdf_text(response.content)
    assert "Design" in text
    assert "Development" in text
    assert "QA" in text


def test_pdf_generation_no_tax_no_notes(client):
    invoice = draft_invoice_with_item(client)  # default: no tax, no notes
    response = client.get(f"/invoices/{invoice['id']}/pdf")
    assert response.status_code == 200
    text = _extract_pdf_text(response.content)
    assert "Tax" not in text  # tax row should be hidden when tax_rate is 0


def test_pdf_generation_404_for_missing_invoice(client):
    response = client.get("/invoices/does-not-exist/pdf")
    assert response.status_code == 404
