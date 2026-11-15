from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DataSourceStatus(StrictModel):
    source_name: str = Field(min_length=2, max_length=100)
    source_type: Literal["paytm_settlement", "account_aggregator", "bill_registry"]
    last_synced_minutes_ago: int = Field(ge=0, le=100_000)
    status: Literal["FRESH", "STALE", "DISCONNECTED"]
    coverage_note: str = Field(default="Demo source", max_length=240)


class LiabilityItem(StrictModel):
    id: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=2, max_length=100)
    category: Literal["supplier", "rent", "utilities", "payroll", "emi", "tax", "other"]
    amount: float = Field(gt=0, le=100_000_000)
    due_in_days: int = Field(ge=0, le=365)
    recurrence: Literal["one_time", "weekly", "monthly"] = "one_time"
    priority: Literal["critical", "high", "medium"] = "medium"


class DailyCashflow(StrictModel):
    date: str
    upi_inflow: float = Field(ge=0, le=100_000_000)
    outflow: float = Field(ge=0, le=100_000_000, description="Declared routine operating outflows; exclude liabilities listed separately.")
    net_flow: float | None = None

    @field_validator("date")
    @classmethod
    def validate_iso_date(cls, value: str) -> str:
        from datetime import date

        try:
            date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("date must use YYYY-MM-DD format") from exc
        return value


class MerchantEvaluationRequest(StrictModel):
    merchant_id: str = Field(default="PYTM-MERCH-88421", min_length=3, max_length=80)
    shop_name: str = Field(default="Sri Murugan Departmental Store", min_length=2, max_length=120)
    available_balance: float = Field(default=42_000, ge=0, le=100_000_000)
    horizon_days: int = Field(default=14, ge=7, le=30)
    data_sources: list[DataSourceStatus] = Field(min_length=1, max_length=10)
    liabilities: list[LiabilityItem] = Field(default_factory=list, max_length=100)
    recent_cashflows: list[DailyCashflow] = Field(default_factory=list, max_length=90)
    seasonality_mode: Literal["normal", "festive_surge", "crunch_warning"] = "normal"
    custom_buffer_override: float | None = Field(default=None, ge=0, le=100_000_000)
    cashflow_scope: Literal["upi_only", "multi_channel"] = "upi_only"


class ForecastDay(StrictModel):
    day: int
    date: str
    conservative_inflow: float
    stressed_operating_outflow: float
    due_liabilities: float
    projected_closing_balance: float


class SafeToReserveResponse(StrictModel):
    generated_at: str
    merchant_id: str
    freshness_grade: Literal["HIGH_TRUST", "DEGRADED_STALE", "UNRELIABLE_HALT"]
    max_stale_minutes: int
    data_quality_score: int = Field(ge=0, le=100)
    history_days: int
    due_0_to_3_days: float
    due_4_to_7_days: float
    due_8_to_14_days: float
    due_15_to_30_days: float
    total_horizon_liabilities: float
    available_balance: float
    p20_daily_inflow: float
    p80_daily_operating_outflow: float
    working_capital_buffer: float
    projected_min_balance: float
    safe_surplus: float
    recommended_reserve: float
    reserve_status: Literal["READY_TO_RESERVE", "CAUTIOUS_RESERVE", "PAUSE_RECOMMENDED", "DATA_STALE_HOLD", "DATA_INSUFFICIENT_HOLD"]
    uncertainty_band: str
    risk_flags: list[str]
    calibration_factors: list[str]
    reasoning_steps: list[str]
    decision_explanation: str
    forecast: list[ForecastDay]


class ReserveDecisionRequest(StrictModel):
    evaluation_request: MerchantEvaluationRequest
    action: Literal["APPROVED", "MODIFIED_APPROVED", "SKIPPED"]
    requested_amount: float = Field(ge=0, le=100_000_000)


class LedgerEntry(StrictModel):
    entry_id: str
    merchant_id: str
    timestamp: str
    action: Literal["APPROVED", "MODIFIED_APPROVED", "SKIPPED"]
    recommended_amount: float
    executed_amount: float
    instrument_split: dict[str, float]
    settlement_ref: str
    balance_before: float
    balance_after: float
    data_quality_score: int
    simulated: bool = True


class InvoiceLineItem(StrictModel):
    product_name: str = Field(min_length=1, max_length=180)
    normalized_product_name: str = Field(default="", max_length=180)
    quantity: float | None = Field(default=None, ge=0, le=100_000_000)
    unit: str | None = Field(default=None, max_length=40)
    unit_price: float | None = Field(default=None, ge=0, le=100_000_000)
    line_total: float | None = Field(default=None, ge=0, le=100_000_000)
    sku: str | None = Field(default=None, max_length=80)


class InvoiceDraft(StrictModel):
    supplier_name: str | None = Field(default=None, max_length=160)
    invoice_number: str | None = Field(default=None, max_length=100)
    invoice_date: str | None = None
    due_date: str | None = None
    currency: str = Field(default="INR", min_length=3, max_length=8)
    subtotal: float | None = Field(default=None, ge=0, le=100_000_000)
    tax_amount: float | None = Field(default=None, ge=0, le=100_000_000)
    total_amount: float | None = Field(default=None, ge=0, le=100_000_000)
    amount_paid: float | None = Field(default=None, ge=0, le=100_000_000)
    items: list[InvoiceLineItem] = Field(default_factory=list, max_length=200)
    warnings: list[str] = Field(default_factory=list, max_length=40)
    requires_review: bool = True
    extraction_model: str | None = None

    @field_validator("invoice_date", "due_date")
    @classmethod
    def validate_optional_iso_date(cls, value: str | None) -> str | None:
        if value is None or value.strip() == "":
            return None
        from datetime import date

        try:
            date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("date must use YYYY-MM-DD format") from exc
        return value


class InvoiceExtractRequest(StrictModel):
    merchant_id: str = Field(min_length=3, max_length=80)
    filename: str = Field(min_length=1, max_length=180)
    mime_type: Literal["image/jpeg", "image/png", "image/webp", "application/pdf"]
    image_base64: str = Field(min_length=100, max_length=7_500_000)


class InvoiceExtractResponse(StrictModel):
    draft: InvoiceDraft
    model: str
    provider: Literal["Sarvam AI"] = "Sarvam AI"
    requires_merchant_review: bool = True


class InvoiceConfirmRequest(StrictModel):
    merchant_id: str = Field(min_length=3, max_length=80)
    invoice: InvoiceDraft


class ConfirmedInvoice(StrictModel):
    invoice_id: str
    merchant_id: str
    status: Literal["CONFIRMED_BY_MERCHANT"]
    created_at: str
    invoice: InvoiceDraft


class SaleRecordCreate(StrictModel):
    merchant_id: str = Field(min_length=3, max_length=80)
    product_name: str = Field(min_length=1, max_length=180)
    normalized_product_name: str = Field(default="", max_length=180)
    quantity: float = Field(gt=0, le=100_000_000)
    unit: str = Field(min_length=1, max_length=40)
    unit_selling_price: float = Field(gt=0, le=100_000_000)
    sale_date: str
    source: Literal["manual", "pos_import"] = "manual"

    @field_validator("sale_date")
    @classmethod
    def validate_sale_date(cls, value: str) -> str:
        from datetime import date

        try:
            date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("sale_date must use YYYY-MM-DD format") from exc
        return value


class MerchantTrendResponse(StrictModel):
    merchant_id: str
    generated_at: str
    invoice_count: int
    sales_record_count_30d: int
    purchase_trends: list[dict]
    sales_trends_30d: list[dict]
    llm_narrative: str
    llm_status: Literal["GENERATED", "NOT_CONFIGURED", "UPSTREAM_ERROR"]
    llm_model: str
    data_limitations: list[str]
    llm_caveats: list[str] = Field(default_factory=list)
