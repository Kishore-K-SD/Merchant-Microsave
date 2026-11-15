import base64
from datetime import date

from fastapi.testclient import TestClient

from app.main import app
from app.models.schemas import InvoiceDraft, InvoiceLineItem
from app.services import purchase_service, sarvam_service


def _invoice_payload(merchant_id: str = "TEST-MERCH-1", invoice_number: str = "INV-001") -> dict:
    return {
        "merchant_id": merchant_id,
        "invoice": {
            "supplier_name": "ABC Wholesale",
            "invoice_number": invoice_number,
            "invoice_date": "2026-11-01",
            "due_date": "2026-11-10",
            "currency": "INR",
            "subtotal": 5000,
            "tax_amount": 250,
            "total_amount": 5250,
            "amount_paid": 1000,
            "items": [
                {
                    "product_name": "Premium Rice 25 kg",
                    "normalized_product_name": "Premium Rice 25 kg",
                    "quantity": 25,
                    "unit": "kg",
                    "unit_price": 200,
                    "line_total": 5000,
                }
            ],
            "warnings": [],
            "requires_review": True,
            "extraction_model": "gemma4",
        },
    }


def test_invoice_image_extraction_calls_mocked_gemma(monkeypatch):
    async def fake_extract(_image: bytes, _mime: str) -> InvoiceDraft:
        return InvoiceDraft(
            supplier_name="ABC Wholesale",
            invoice_number="INV-001",
            invoice_date="2026-11-01",
            total_amount=5250,
            items=[InvoiceLineItem(product_name="Rice", quantity=25, unit="kg", unit_price=200)],
            extraction_model="gemma4",
        )

    monkeypatch.setattr(sarvam_service, "extract_invoice_from_document", fake_extract)
    client = TestClient(app)
    response = client.post(
        "/api/v1/microsave/invoices/extract",
        json={
            "merchant_id": "TEST-MERCH-1",
            "filename": "invoice.jpg",
            "mime_type": "image/jpeg",
            "image_base64": base64.b64encode(b"\xff\xd8\xff" + b"test-image-bytes" * 10).decode("ascii"),
        },
    )
    assert response.status_code == 200
    assert response.json()["draft"]["supplier_name"] == "ABC Wholesale"
    assert response.json()["model"] == "gemma4"
    assert response.json()["requires_merchant_review"] is True


def test_invalid_base64_invoice_is_rejected():
    client = TestClient(app)
    response = client.post(
        "/api/v1/microsave/invoices/extract",
        json={
            "merchant_id": "TEST-MERCH-1",
            "filename": "invoice.jpg",
            "mime_type": "image/jpeg",
            "image_base64": "!" * 120,
        },
    )
    assert response.status_code == 422


def test_confirmed_invoices_create_price_trends_and_duplicate_guard(tmp_path, monkeypatch):
    monkeypatch.setattr(purchase_service, "DB_PATH", tmp_path / "purchases.sqlite3")
    client = TestClient(app)
    first = client.post("/api/v1/microsave/invoices/confirm", json=_invoice_payload())
    assert first.status_code == 200
    assert first.json()["status"] == "CONFIRMED_BY_MERCHANT"

    duplicate = client.post("/api/v1/microsave/invoices/confirm", json=_invoice_payload())
    assert duplicate.status_code == 409

    trends = client.get("/api/v1/microsave/insights/TEST-MERCH-1")
    assert trends.status_code == 200
    assert trends.json()["invoice_count"] == 1
    assert trends.json()["purchase_trends"][0]["latest_observed_unit_price"] == 200
    assert "stock" in " ".join(trends.json()["data_limitations"]).lower()


def test_sales_records_are_separate_from_payment_collections(tmp_path, monkeypatch):
    monkeypatch.setattr(purchase_service, "DB_PATH", tmp_path / "sales.sqlite3")
    monkeypatch.setattr(sarvam_service, "sarvam_configured", lambda: False)
    client = TestClient(app)
    response = client.post(
        "/api/v1/microsave/sales",
        json={
            "merchant_id": "TEST-MERCH-2",
            "product_name": "Rice 1kg",
            "normalized_product_name": "Rice 1kg",
            "quantity": 4,
            "unit": "pack",
            "unit_selling_price": 65,
            "sale_date": date.today().isoformat(),
            "source": "manual",
        },
    )
    assert response.status_code == 200
    trends = client.get("/api/v1/microsave/insights/TEST-MERCH-2")
    assert trends.status_code == 200
    body = trends.json()
    assert body["sales_record_count_30d"] == 1
    assert body["sales_trends_30d"][0]["quantity_sold_30d"] == 4
    assert body["llm_status"] == "NOT_CONFIGURED"


def test_sarvam_chat_completion_uses_gemma4_and_subscription_key(monkeypatch):
    import asyncio

    captured = {}

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"choices": [{"message": {"content": '{"ok": true}'}}]}

    class FakeAsyncClient:
        def __init__(self, timeout):
            captured["timeout"] = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, url, headers, json):
            captured.update({"url": url, "headers": headers, "payload": json})
            return FakeResponse()

    monkeypatch.setenv("SARVAM_API_KEY", "mock-sarvam-key")
    monkeypatch.setenv("SARVAM_MODEL", "gemma4")
    monkeypatch.setattr(sarvam_service.httpx, "AsyncClient", FakeAsyncClient)
    output = asyncio.run(sarvam_service.complete_chat([{"role": "user", "content": "test"}]))

    assert output == '{"ok": true}'
    assert captured["url"] == "https://api.sarvam.ai/v2/chat/completions"
    assert captured["headers"]["api-subscription-key"] == "mock-sarvam-key"
    assert captured["payload"]["model"] == "gemma4"
    assert captured["payload"]["response_format"] == {"type": "json_object"}


def test_invoice_extraction_parses_mocked_gemma_json(monkeypatch):
    import asyncio

    captured = {}

    async def fake_completion(messages, *, max_tokens=1800):
        assert max_tokens == 3000
        captured["messages"] = messages
        return (
            '{"supplier_name":"Mock Suppliers","invoice_number":"M-77",'
            '"invoice_date":"2026-11-12","due_date":null,"currency":"INR",'
            '"subtotal":1200,"tax_amount":60,"total_amount":1260,"amount_paid":0,'
            '"items":[{"product_name":"Sunflower Oil 1L","normalized_product_name":"Sunflower Oil 1L",'
            '"quantity":12,"unit":"bottle","unit_price":100,"line_total":1200,"sku":null}],'
            '"warnings":[]}'
        )

    monkeypatch.setattr(sarvam_service, "complete_chat", fake_completion)
    draft = asyncio.run(sarvam_service.extract_invoice_from_document(b"\xff\xd8\xffmock-image", "image/jpeg"))
    assert draft.supplier_name == "Mock Suppliers"
    assert draft.items[0].quantity == 12
    assert draft.requires_review is True
    assert draft.extraction_model == "gemma4"
    image_part = captured["messages"][1]["content"][1]
    assert image_part["image_url"]["url"].startswith("data:image/jpeg;base64,")


def test_pdf_invoice_is_rendered_to_inline_image_parts_and_truncated_with_warning():
    import fitz

    document = fitz.open()
    for index in range(4):
        page = document.new_page()
        page.insert_text((72, 72), f"Invoice page {index + 1}")
    pdf_bytes = document.tobytes()
    document.close()

    parts, warnings = sarvam_service._document_image_parts(pdf_bytes, "application/pdf")
    assert len(parts) == 3
    assert all(part["image_url"]["url"].startswith("data:image/jpeg;base64,") for part in parts)
    assert warnings and "only the first 3 pages" in warnings[0]


def test_confirm_invoice_rejects_missing_quantity_or_paid_amount(tmp_path, monkeypatch):
    monkeypatch.setattr(purchase_service, "DB_PATH", tmp_path / "incomplete.sqlite3")
    client = TestClient(app)
    payload = _invoice_payload(merchant_id="TEST-MERCH-3", invoice_number="INV-INCOMPLETE")
    payload["invoice"]["amount_paid"] = None
    assert client.post("/api/v1/microsave/invoices/confirm", json=payload).status_code == 409

    payload["invoice"]["amount_paid"] = 0
    payload["invoice"]["items"][0]["quantity"] = None
    assert client.post("/api/v1/microsave/invoices/confirm", json=payload).status_code == 409
