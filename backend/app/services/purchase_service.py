"""Persistence and deterministic trend calculations for merchant purchases/sales."""
from __future__ import annotations

import json
import os
import sqlite3
import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.models.schemas import ConfirmedInvoice, InvoiceConfirmRequest, SaleRecordCreate

_DEFAULT_DB = Path(__file__).resolve().parents[2] / "data" / "microsave_demo.db"
DB_PATH = Path(os.getenv("MICROSAVE_DB_PATH", str(_DEFAULT_DB)))


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS supplier_invoices (
                invoice_id TEXT PRIMARY KEY,
                merchant_id TEXT NOT NULL,
                supplier_name TEXT NOT NULL,
                invoice_number TEXT,
                invoice_date TEXT,
                due_date TEXT,
                total_amount REAL NOT NULL,
                amount_paid REAL NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )"""
        )
        conn.execute(
            """CREATE INDEX IF NOT EXISTS idx_supplier_invoice_merchant_date
               ON supplier_invoices(merchant_id, invoice_date)"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS sales_records (
                sale_id TEXT PRIMARY KEY,
                merchant_id TEXT NOT NULL,
                product_name TEXT NOT NULL,
                normalized_product_name TEXT NOT NULL,
                quantity REAL NOT NULL,
                unit TEXT NOT NULL,
                unit_selling_price REAL NOT NULL,
                sale_date TEXT NOT NULL,
                source TEXT NOT NULL,
                created_at TEXT NOT NULL
            )"""
        )
        conn.execute(
            """CREATE INDEX IF NOT EXISTS idx_sales_merchant_date
               ON sales_records(merchant_id, sale_date)"""
        )


def save_invoice(payload: InvoiceConfirmRequest) -> ConfirmedInvoice:
    init_db()
    invoice = payload.invoice
    if not invoice.supplier_name or not invoice.supplier_name.strip():
        raise ValueError("Supplier name is required before confirming an invoice.")
    if invoice.total_amount is None or invoice.total_amount <= 0:
        raise ValueError("A valid invoice total is required before confirming an invoice.")
    if invoice.amount_paid is None:
        raise ValueError("Confirm the amount already paid before saving this invoice.")
    if invoice.amount_paid > invoice.total_amount:
        raise ValueError("Amount already paid cannot exceed the invoice total.")
    if not invoice.items:
        raise ValueError("At least one invoice line item is required before confirming an invoice.")
    for item in invoice.items:
        if item.quantity is None or item.quantity <= 0 or not item.unit or not item.unit.strip():
            raise ValueError(f"Add a valid quantity and unit for '{item.product_name}' before confirming the invoice.")
        if item.unit_price is None and item.line_total is None:
            raise ValueError(f"Add a unit price or line total for '{item.product_name}' before confirming the invoice.")

    if invoice.invoice_number:
        with _connect() as conn:
            duplicate = conn.execute(
                "SELECT invoice_id FROM supplier_invoices WHERE merchant_id = ? AND supplier_name = ? AND invoice_number = ?",
                (payload.merchant_id, invoice.supplier_name.strip(), invoice.invoice_number.strip()),
            ).fetchone()
        if duplicate:
            raise ValueError("This supplier invoice number is already recorded for this merchant.")

    invoice_id = f"PUR-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"
    created_at = datetime.now(timezone.utc).isoformat()
    invoice_payload = invoice.model_dump(mode="json")
    with _connect() as conn:
        conn.execute(
            """INSERT INTO supplier_invoices
               (invoice_id, merchant_id, supplier_name, invoice_number, invoice_date, due_date,
                total_amount, amount_paid, payload_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                invoice_id,
                payload.merchant_id,
                invoice.supplier_name.strip(),
                invoice.invoice_number,
                invoice.invoice_date,
                invoice.due_date,
                float(invoice.total_amount),
                float(invoice.amount_paid or 0),
                json.dumps(invoice_payload, ensure_ascii=False),
                created_at,
            ),
        )
    return ConfirmedInvoice(
        invoice_id=invoice_id,
        merchant_id=payload.merchant_id,
        status="CONFIRMED_BY_MERCHANT",
        created_at=created_at,
        invoice=invoice,
    )


def list_invoices(merchant_id: str) -> list[ConfirmedInvoice]:
    init_db()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM supplier_invoices WHERE merchant_id = ? ORDER BY COALESCE(invoice_date, created_at) DESC LIMIT 250",
            (merchant_id,),
        ).fetchall()
    return [
        ConfirmedInvoice(
            invoice_id=row["invoice_id"],
            merchant_id=row["merchant_id"],
            status="CONFIRMED_BY_MERCHANT",
            created_at=row["created_at"],
            invoice=json.loads(row["payload_json"]),
        )
        for row in rows
    ]


def save_sale(payload: SaleRecordCreate) -> dict[str, Any]:
    init_db()
    sale_id = f"SALE-{uuid.uuid4().hex[:10].upper()}"
    created_at = datetime.now(timezone.utc).isoformat()
    normalized = payload.normalized_product_name or " ".join(payload.product_name.lower().split())
    with _connect() as conn:
        conn.execute(
            """INSERT INTO sales_records
               (sale_id, merchant_id, product_name, normalized_product_name, quantity, unit,
                unit_selling_price, sale_date, source, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                sale_id, payload.merchant_id, payload.product_name.strip(), normalized.strip(),
                payload.quantity, payload.unit.strip(), payload.unit_selling_price,
                payload.sale_date, payload.source, created_at,
            ),
        )
    return {
        "sale_id": sale_id,
        "merchant_id": payload.merchant_id,
        "product_name": payload.product_name,
        "quantity": payload.quantity,
        "unit": payload.unit,
        "unit_selling_price": payload.unit_selling_price,
        "sale_date": payload.sale_date,
        "source": payload.source,
        "created_at": created_at,
    }


def build_trend_data(merchant_id: str) -> dict[str, Any]:
    """Calculate observable purchase-price and recorded sales trends; no LLM math."""
    init_db()
    with _connect() as conn:
        invoice_rows = conn.execute(
            "SELECT * FROM supplier_invoices WHERE merchant_id = ? ORDER BY COALESCE(invoice_date, created_at) ASC",
            (merchant_id,),
        ).fetchall()
        sales_rows = conn.execute(
            "SELECT * FROM sales_records WHERE merchant_id = ? ORDER BY sale_date ASC",
            (merchant_id,),
        ).fetchall()

    purchase_groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for invoice_row in invoice_rows:
        payload = json.loads(invoice_row["payload_json"])
        observed_date = invoice_row["invoice_date"] or invoice_row["created_at"][:10]
        supplier = invoice_row["supplier_name"]
        for item in payload.get("items", []):
            product = str(item.get("normalized_product_name") or item.get("product_name") or "").strip()
            unit = str(item.get("unit") or "unit").strip().lower()
            quantity = item.get("quantity")
            price = item.get("unit_price")
            line_total = item.get("line_total")
            if price is None and quantity not in (None, 0) and line_total is not None:
                price = float(line_total) / float(quantity)
            if not product:
                continue
            purchase_groups[(product.casefold(), unit)].append(
                {
                    "product_name": product,
                    "unit": unit,
                    "quantity": float(quantity) if quantity is not None else None,
                    "unit_price": float(price) if price is not None else None,
                    "date": observed_date,
                    "supplier_name": supplier,
                }
            )

    purchase_trends: list[dict[str, Any]] = []
    for entries in purchase_groups.values():
        entries.sort(key=lambda entry: entry["date"])
        priced = [entry for entry in entries if entry["unit_price"] is not None]
        first_price = priced[0]["unit_price"] if priced else None
        latest_price = priced[-1]["unit_price"] if priced else None
        price_change_pct = None
        if first_price is not None and first_price > 0 and latest_price is not None:
            price_change_pct = round((latest_price - first_price) / first_price * 100, 2)
        purchase_trends.append(
            {
                "product_name": entries[-1]["product_name"],
                "unit": entries[-1]["unit"],
                "purchase_line_count": len(entries),
                "total_recorded_quantity": round(sum(entry["quantity"] or 0 for entry in entries), 3),
                "first_observed_unit_price": round(first_price, 2) if first_price is not None else None,
                "latest_observed_unit_price": round(latest_price, 2) if latest_price is not None else None,
                "price_change_pct": price_change_pct,
                "first_purchase_date": entries[0]["date"],
                "last_purchase_date": entries[-1]["date"],
            }
        )

    today = date.today()
    window_start = today - timedelta(days=29)
    sales_groups: dict[tuple[str, str], list[sqlite3.Row]] = defaultdict(list)
    for row in sales_rows:
        try:
            sale_day = date.fromisoformat(row["sale_date"])
        except ValueError:
            continue
        if window_start <= sale_day <= today:
            sales_groups[(row["normalized_product_name"].casefold(), row["unit"].lower())].append(row)

    sales_trends: list[dict[str, Any]] = []
    for entries in sales_groups.values():
        sales_trends.append(
            {
                "product_name": entries[-1]["product_name"],
                "unit": entries[-1]["unit"],
                "record_count_30d": len(entries),
                "quantity_sold_30d": round(sum(float(row["quantity"]) for row in entries), 3),
                "average_selling_price": round(
                    sum(float(row["quantity"]) * float(row["unit_selling_price"]) for row in entries)
                    / max(sum(float(row["quantity"]) for row in entries), 0.000001),
                    2,
                ),
                "last_sale_date": entries[-1]["sale_date"],
            }
        )
    sales_trends.sort(key=lambda item: item["quantity_sold_30d"], reverse=True)
    purchase_trends.sort(key=lambda item: item["product_name"].casefold())

    return {
        "merchant_id": merchant_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "invoice_count": len(invoice_rows),
        "sales_record_count_30d": sum(item["record_count_30d"] for item in sales_trends),
        "purchase_trends": purchase_trends,
        "sales_trends_30d": sales_trends,
        "data_limitations": [
            "Purchase trends are based only on merchant-confirmed invoices recorded in MicroSave.",
            "Sales trends are based only on manually entered or imported item-level sales records from the last 30 days.",
            "Current inventory cannot be inferred without an opening stock count and adjustments for returns, damage and wastage.",
            "No supplier price feed is connected; future price changes are not known until a new invoice or quote is recorded.",
        ],
    }
