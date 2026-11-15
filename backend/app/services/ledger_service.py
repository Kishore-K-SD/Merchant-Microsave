from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.models.schemas import LedgerEntry

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
            """CREATE TABLE IF NOT EXISTS reserve_ledger (
                entry_id TEXT PRIMARY KEY,
                merchant_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                action TEXT NOT NULL,
                recommended_amount REAL NOT NULL,
                executed_amount REAL NOT NULL,
                instrument_split TEXT NOT NULL,
                settlement_ref TEXT NOT NULL,
                balance_before REAL NOT NULL,
                balance_after REAL NOT NULL,
                data_quality_score INTEGER NOT NULL,
                simulated INTEGER NOT NULL DEFAULT 1
            )"""
        )


def record_decision(
    merchant_id: str,
    action: str,
    recommended_amount: float,
    executed_amount: float,
    balance_before: float,
    data_quality_score: int,
) -> LedgerEntry:
    init_db()
    now = datetime.now(timezone.utc)
    amount = round(executed_amount, 2)
    entry_id = f"DEMO-RES-{now.strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
    reference = f"SIMULATED-{uuid.uuid4().hex[:10].upper()}" if amount > 0 else "NO-TRANSFER-SKIPPED"
    entry = LedgerEntry(
        entry_id=entry_id,
        merchant_id=merchant_id,
        timestamp=now.isoformat(),
        action=action,
        recommended_amount=round(recommended_amount, 2),
        executed_amount=amount,
        instrument_split={"demo_reserve_wallet": amount},
        settlement_ref=reference,
        balance_before=round(balance_before, 2),
        balance_after=round(balance_before - amount, 2),
        data_quality_score=data_quality_score,
        simulated=True,
    )
    with _connect() as conn:
        conn.execute(
            """INSERT INTO reserve_ledger VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                entry.entry_id, entry.merchant_id, entry.timestamp, entry.action,
                entry.recommended_amount, entry.executed_amount,
                json.dumps(entry.instrument_split), entry.settlement_ref,
                entry.balance_before, entry.balance_after, entry.data_quality_score, 1,
            ),
        )
    return entry


def fetch_ledger(merchant_id: str) -> list[LedgerEntry]:
    init_db()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM reserve_ledger WHERE merchant_id = ? ORDER BY timestamp DESC LIMIT 100",
            (merchant_id,),
        ).fetchall()
    return [
        LedgerEntry(
            entry_id=row["entry_id"],
            merchant_id=row["merchant_id"],
            timestamp=row["timestamp"],
            action=row["action"],
            recommended_amount=row["recommended_amount"],
            executed_amount=row["executed_amount"],
            instrument_split=json.loads(row["instrument_split"]),
            settlement_ref=row["settlement_ref"],
            balance_before=row["balance_before"],
            balance_after=row["balance_after"],
            data_quality_score=row["data_quality_score"],
            simulated=bool(row["simulated"]),
        )
        for row in rows
    ]
