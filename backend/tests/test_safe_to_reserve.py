from app.agents.safe_to_reserve_graph import evaluate_merchant
from app.demo_data import build_demo_request


def test_demo_scenario_produces_explainable_recommendation():
    req = build_demo_request()
    result = evaluate_merchant(req)

    assert result.recommended_reserve > 0
    assert result.safe_surplus >= result.recommended_reserve
    assert result.working_capital_buffer >= 5_000
    assert result.history_days == 30
    assert result.forecast[0].day == 1
    assert result.forecast[-1].day == req.horizon_days
    assert "UPI-only" in " ".join(result.risk_flags)
    assert result.data_quality_score < 100


def test_disconnected_or_very_stale_source_halts_reserve():
    req = build_demo_request()
    req.data_sources[0].status = "DISCONNECTED"
    result = evaluate_merchant(req)

    assert result.freshness_grade == "UNRELIABLE_HALT"
    assert result.recommended_reserve == 0
    assert result.reserve_status == "DATA_STALE_HOLD"


def test_insufficient_history_halts_reserve():
    req = build_demo_request()
    req.recent_cashflows = req.recent_cashflows[-5:]
    result = evaluate_merchant(req)

    assert result.reserve_status == "DATA_INSUFFICIENT_HOLD"
    assert result.recommended_reserve == 0


def test_stale_history_halts_reserve():
    req = build_demo_request()
    for index, row in enumerate(req.recent_cashflows):
        row.date = f"2020-01-{(index % 28) + 1:02d}"
    result = evaluate_merchant(req)

    assert result.reserve_status == "DATA_INSUFFICIENT_HOLD"
    assert result.recommended_reserve == 0


def test_custom_buffer_cannot_reduce_safety_floor():
    base = build_demo_request()
    without_override = evaluate_merchant(base)
    adjusted = build_demo_request()
    adjusted.custom_buffer_override = 100
    with_override = evaluate_merchant(adjusted)

    assert with_override.working_capital_buffer >= without_override.working_capital_buffer
    assert with_override.safe_surplus <= without_override.safe_surplus


def test_liability_due_today_is_included_in_first_forecast_day():
    req = build_demo_request()
    req.liabilities[0].due_in_days = 0
    result = evaluate_merchant(req)

    assert result.due_0_to_3_days >= req.liabilities[0].amount
    assert result.forecast[0].due_liabilities >= req.liabilities[0].amount


def test_weekly_liability_is_expanded_within_horizon():
    req = build_demo_request()
    req.liabilities = [req.liabilities[0].model_copy(update={"due_in_days": 1, "recurrence": "weekly"})]
    result = evaluate_merchant(req)

    assert result.total_horizon_liabilities == req.liabilities[0].amount * 2


def test_slow_sales_reduce_or_pause_recommendation():
    normal = build_demo_request()
    baseline = evaluate_merchant(normal)
    slow = build_demo_request()
    slow.recent_cashflows = [
        row.model_copy(update={"upi_inflow": row.upi_inflow * (0.35 if index >= 23 else 1.0)})
        for index, row in enumerate(slow.recent_cashflows)
    ]
    stressed = evaluate_merchant(slow)

    assert stressed.recommended_reserve <= baseline.recommended_reserve


def test_stale_source_is_haircut_and_explained():
    req = build_demo_request()
    req.data_sources[1].status = "STALE"
    req.data_sources[1].last_synced_minutes_ago = 90
    result = evaluate_merchant(req)

    assert result.freshness_grade == "DEGRADED_STALE"
    assert any("50%" in item for item in result.risk_flags)
