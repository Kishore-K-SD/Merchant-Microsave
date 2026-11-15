from __future__ import annotations

import base64
import binascii
import json

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.agents.safe_to_reserve_graph import evaluate_merchant
from app.demo_data import build_demo_request
from app.models.schemas import (
    ConfirmedInvoice,
    InvoiceConfirmRequest,
    InvoiceExtractRequest,
    InvoiceExtractResponse,
    LedgerEntry,
    MerchantEvaluationRequest,
    MerchantTrendResponse,
    ReserveDecisionRequest,
    SafeToReserveResponse,
    SaleRecordCreate,
)
from app.services.ledger_service import fetch_ledger, init_db, record_decision
from app.services import purchase_service, sarvam_service
from app.services.sarvam_service import SarvamAPIError, SarvamConfigurationError

app = FastAPI(
    title="Merchant MicroSave Demo API",
    version="3.0.0",
    description="Hackathon prototype. All bundled financial data and reserve entries are simulated.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)


@app.on_event("startup")
def startup_event() -> None:
    init_db()
    purchase_service.init_db()


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "mode": "DEMO",
        "money_movement": "SIMULATED_ONLY",
        "llm_provider": "Sarvam AI",
        "llm_model": sarvam_service.sarvam_model_name(),
        "llm_configured": str(sarvam_service.sarvam_configured()).lower(),
    }


@app.get("/api/v1/microsave/demo-data", response_model=MerchantEvaluationRequest)
def demo_data() -> MerchantEvaluationRequest:
    return build_demo_request()


@app.post("/api/v1/microsave/evaluate", response_model=SafeToReserveResponse)
def evaluate(payload: MerchantEvaluationRequest) -> SafeToReserveResponse:
    return evaluate_merchant(payload)


@app.post("/api/v1/microsave/invoices/extract", response_model=InvoiceExtractResponse)
async def extract_supplier_invoice(payload: InvoiceExtractRequest) -> InvoiceExtractResponse:
    """Use Gemma 4 31B vision to extract an invoice document into a reviewable draft."""
    try:
        image_bytes = base64.b64decode(payload.image_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status_code=422, detail="image_base64 must be valid base64 data.") from exc
    if not image_bytes or len(image_bytes) > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Invoice files must be between 1 byte and 5 MB.")
    document_signatures = {
        "image/jpeg": image_bytes.startswith(b"\xff\xd8\xff"),
        "image/png": image_bytes.startswith(b"\x89PNG\r\n\x1a\n"),
        "image/webp": len(image_bytes) >= 12 and image_bytes.startswith(b"RIFF") and image_bytes[8:12] == b"WEBP",
        "application/pdf": image_bytes.startswith(b"%PDF-"),
    }
    if not document_signatures.get(payload.mime_type, False):
        raise HTTPException(status_code=415, detail="The file content does not match its declared JPG, PNG, WEBP or PDF type.")

    try:
        draft = await sarvam_service.extract_invoice_from_document(image_bytes, payload.mime_type)
    except SarvamConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except SarvamAPIError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return InvoiceExtractResponse(draft=draft, model=sarvam_service.sarvam_model_name())


@app.post("/api/v1/microsave/invoices/confirm", response_model=ConfirmedInvoice)
def confirm_supplier_invoice(payload: InvoiceConfirmRequest) -> ConfirmedInvoice:
    """Persist an invoice only after merchant review and explicit confirmation."""
    try:
        return purchase_service.save_invoice(payload)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/api/v1/microsave/invoices/{merchant_id}", response_model=list[ConfirmedInvoice])
def get_supplier_invoices(merchant_id: str) -> list[ConfirmedInvoice]:
    if not merchant_id.strip():
        raise HTTPException(status_code=400, detail="merchant_id cannot be empty")
    return purchase_service.list_invoices(merchant_id)


@app.post("/api/v1/microsave/sales", response_model=dict)
def record_item_sale(payload: SaleRecordCreate) -> dict:
    """Record or import item-level sales; this is separate from Paytm QR collections."""
    return purchase_service.save_sale(payload)


@app.get("/api/v1/microsave/insights/{merchant_id}", response_model=MerchantTrendResponse)
async def get_merchant_insights(merchant_id: str) -> MerchantTrendResponse:
    if not merchant_id.strip():
        raise HTTPException(status_code=400, detail="merchant_id cannot be empty")
    trends = purchase_service.build_trend_data(merchant_id)
    deterministic_fallback = (
        f"MicroSave has {trends['invoice_count']} merchant-confirmed supplier invoice(s) and "
        f"{trends['sales_record_count_30d']} item-level sales record(s) in the last 30 days. "
        "Purchase-price observations are calculated from recorded invoice line items. "
        "Sales demand is only visible for products with recorded item-level sales; current stock "
        "is not inferred without an opening stock count and stock adjustments."
    )
    llm_status = "NOT_CONFIGURED"
    narrative = deterministic_fallback
    caveats: list[str] = []
    if sarvam_service.sarvam_configured():
        try:
            raw = await sarvam_service.explain_merchant_trends(trends)
            parsed = json.loads(raw)
            narrative = parsed["narrative"]
            caveats = parsed.get("caveats", [])
            llm_status = "GENERATED"
        except (SarvamConfigurationError, SarvamAPIError, ValueError, KeyError, TypeError):
            llm_status = "UPSTREAM_ERROR"
            caveats = ["AI narrative is unavailable; showing deterministic trend data only."]

    return MerchantTrendResponse(
        merchant_id=merchant_id,
        generated_at=trends["generated_at"],
        invoice_count=trends["invoice_count"],
        sales_record_count_30d=trends["sales_record_count_30d"],
        purchase_trends=trends["purchase_trends"],
        sales_trends_30d=trends["sales_trends_30d"],
        llm_narrative=narrative,
        llm_status=llm_status,
        llm_model=sarvam_service.sarvam_model_name(),
        data_limitations=trends["data_limitations"],
        llm_caveats=caveats,
    )


@app.post("/api/v1/microsave/ledger/commit", response_model=LedgerEntry)
def commit_reserve_decision(payload: ReserveDecisionRequest) -> LedgerEntry:
    # Recompute server-side from the submitted, current demo snapshot. The browser
    # cannot self-declare a larger safe amount or fabricate the recommended amount.
    evaluation = evaluate_merchant(payload.evaluation_request)
    if payload.action == "SKIPPED":
        if payload.requested_amount != 0:
            raise HTTPException(status_code=422, detail="Skipped decisions must have a zero amount.")
        executed = 0.0
    else:
        if evaluation.recommended_reserve <= 0:
            raise HTTPException(status_code=409, detail="MicroSave has paused reserves. There is no amount available to approve.")
        if payload.requested_amount <= 0:
            raise HTTPException(status_code=422, detail="Approved reserve amount must be greater than zero.")
        if payload.requested_amount > evaluation.recommended_reserve:
            raise HTTPException(
                status_code=409,
                detail=f"Amount exceeds the current engine recommendation of ₹{evaluation.recommended_reserve:,.0f}. Recalculate before approval.",
            )
        if round(payload.requested_amount / 100) * 100 != payload.requested_amount:
            raise HTTPException(status_code=422, detail="Reserve amount must be in ₹100 increments.")
        executed = payload.requested_amount

    action = payload.action
    if action != "SKIPPED" and executed < evaluation.recommended_reserve:
        action = "MODIFIED_APPROVED"
    return record_decision(
        merchant_id=evaluation.merchant_id,
        action=action,
        recommended_amount=evaluation.recommended_reserve,
        executed_amount=executed,
        balance_before=evaluation.available_balance,
        data_quality_score=evaluation.data_quality_score,
    )


@app.get("/api/v1/microsave/ledger/{merchant_id}", response_model=list[LedgerEntry])
def get_merchant_ledger(merchant_id: str) -> list[LedgerEntry]:
    if not merchant_id.strip():
        raise HTTPException(status_code=400, detail="merchant_id cannot be empty")
    return fetch_ledger(merchant_id)
