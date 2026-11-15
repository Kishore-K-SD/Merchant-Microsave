from __future__ import annotations

from datetime import date, timedelta

from app.models.schemas import (
    DataSourceStatus,
    DailyCashflow,
    LiabilityItem,
    MerchantEvaluationRequest,
)


def build_demo_request() -> MerchantEvaluationRequest:
    today = date.today()
    cashflows = []
    # Deterministic synthetic values keep the pitch repeatable and explicitly demo-only.
    inflow_pattern = [7200, 8100, 6800, 9200, 7600, 8400, 6100, 7800, 8800, 7000, 8200, 7500, 9000, 6500]
    outflow_pattern = [2700, 3100, 2500, 3300, 2900, 3000, 2600, 3200, 2800, 3000, 2700, 3400, 2900, 2600]
    for index in range(30):
        cashflows.append(
            DailyCashflow(
                date=(today - timedelta(days=29 - index)).isoformat(),
                upi_inflow=float(inflow_pattern[index % len(inflow_pattern)]),
                outflow=float(outflow_pattern[index % len(outflow_pattern)]),
            )
        )

    return MerchantEvaluationRequest(
        merchant_id="PYTM-MERCH-88421",
        shop_name="Sri Murugan Departmental Store",
        available_balance=42_000,
        horizon_days=14,
        cashflow_scope="upi_only",
        data_sources=[
            DataSourceStatus(
                source_name="Paytm QR collections (simulated)",
                source_type="paytm_settlement",
                last_synced_minutes_ago=4,
                status="FRESH",
                coverage_note="Synthetic settlement events for the hackathon demo; not connected to Paytm.",
            ),
            DataSourceStatus(
                source_name="Bank balance feed (simulated)",
                source_type="account_aggregator",
                last_synced_minutes_ago=12,
                status="FRESH",
                coverage_note="Synthetic available-balance snapshot; no Account Aggregator connection.",
            ),
            DataSourceStatus(
                source_name="Supplier bills (merchant-entered demo data)",
                source_type="bill_registry",
                last_synced_minutes_ago=18,
                status="FRESH",
                coverage_note="Bills entered for demonstration; not sourced from GST or an invoice provider.",
            ),
        ],
        recent_cashflows=cashflows,
        liabilities=[
            LiabilityItem(id="liab-1", title="FMCG distributor payment", category="supplier", amount=14_500, due_in_days=2, priority="critical"),
            LiabilityItem(id="liab-2", title="Shop monthly rent", category="rent", amount=8_500, due_in_days=5, priority="critical"),
            LiabilityItem(id="liab-3", title="Staff salary advance", category="payroll", amount=4_000, due_in_days=6, priority="high"),
            LiabilityItem(id="liab-4", title="Commercial electricity bill", category="utilities", amount=2_000, due_in_days=9, priority="medium"),
        ],
        seasonality_mode="normal",
    )
