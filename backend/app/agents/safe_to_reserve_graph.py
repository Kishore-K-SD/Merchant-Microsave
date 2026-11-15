"""Deterministic, risk-first Safe-to-Reserve decision pipeline.

The amount is calculated from conservative quantiles and a day-by-day
liquidity projection. No generative model is permitted to determine money
movement. This keeps the hackathon financial logic reproducible and testable.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from math import ceil, floor
from statistics import mean

import numpy as np

from app.models.schemas import (
    ForecastDay,
    MerchantEvaluationRequest,
    SafeToReserveResponse,
)


MIN_HISTORY_DAYS = 7
_PENNY = 0.01


def _ceil_to(value: float, step: int = 500) -> float:
    return float(ceil(max(0.0, value) / step) * step)


def _floor_to(value: float, step: int = 100) -> float:
    return float(floor(max(0.0, value) / step) * step)


def _scheduled_liabilities(req: MerchantEvaluationRequest) -> dict[int, float]:
    """Expand known one-time/weekly obligations into the forecast horizon."""
    scheduled: dict[int, float] = defaultdict(float)
    for item in req.liabilities:
        # A bill due today is protected in the first forecast day.
        due_day = max(1, item.due_in_days)
        while due_day <= req.horizon_days:
            if due_day >= 1:
                scheduled[due_day] += item.amount
            if item.recurrence != "weekly":
                break
            due_day += 7
    return dict(scheduled)


def _freshness(req: MerchantEvaluationRequest) -> tuple[str, int, float, list[str], list[str]]:
    stale_values = [source.last_synced_minutes_ago for source in req.data_sources]
    max_stale = max(stale_values, default=100_000)
    disconnected = any(source.status == "DISCONNECTED" for source in req.data_sources)
    explicitly_stale = any(source.status == "STALE" for source in req.data_sources)
    flags: list[str] = []
    steps: list[str] = []

    if disconnected or max_stale > 240:
        grade, factor = "UNRELIABLE_HALT", 0.0
        flags.append("At least one required data feed is disconnected or more than four hours old.")
        steps.append(f"Freshness gate: stop. Oldest feed is {max_stale} minutes old.")
    elif explicitly_stale or max_stale > 45:
        grade, factor = "DEGRADED_STALE", 0.5
        flags.append("Data is stale; recommendation is reduced by a conservative 50% haircut.")
        steps.append(f"Freshness gate: degraded. Oldest feed is {max_stale} minutes old; apply 50% haircut.")
    else:
        grade, factor = "HIGH_TRUST", 1.0
        steps.append(f"Freshness gate: all supplied demo feeds are fresh (maximum sync age {max_stale} minutes).")

    return grade, max_stale, factor, flags, steps


def _history_quality(req: MerchantEvaluationRequest) -> tuple[list[dict], int, bool, list[str]]:
    by_date: dict[str, dict] = {}
    for row in req.recent_cashflows:
        by_date[row.date] = {
            "date": row.date,
            "inflow": float(row.upi_inflow),
            "outflow": float(row.outflow),
        }
    rows = [by_date[key] for key in sorted(by_date)]
    flags: list[str] = []
    latest = date.fromisoformat(rows[-1]["date"]) if rows else None
    too_old = latest is None or (date.today() - latest).days > 2
    if len(rows) < MIN_HISTORY_DAYS:
        flags.append(f"Only {len(rows)} distinct cash-flow days are available; at least {MIN_HISTORY_DAYS} are required.")
    if too_old:
        flags.append("Cash-flow history does not include a recent day; forecast is paused until refreshed.")
    return rows, len(rows), (len(rows) >= MIN_HISTORY_DAYS and not too_old), flags


def evaluate_merchant(req: MerchantEvaluationRequest) -> SafeToReserveResponse:
    generated_at = datetime.now(timezone.utc).isoformat()
    freshness_grade, max_stale, freshness_factor, risk_flags, reasoning = _freshness(req)
    rows, history_days, history_usable, history_flags = _history_quality(req)
    risk_flags.extend(history_flags)

    # A stable, sorted date series avoids duplicate dates overweighting a merchant's history.
    inflows = [row["inflow"] for row in rows]
    outflows = [row["outflow"] for row in rows]
    if inflows:
        p20_inflow = float(np.percentile(inflows, 20))
        median_inflow = float(np.median(inflows))
        p80_outflow = float(np.percentile(outflows, 80))
        recent_outflow = mean(outflows[-7:])
        # A recent expense run-rate increase is captured immediately; a falling recent
        # inflow trend reduces expected inflows but an improving trend is not extrapolated.
        trend_factor = 1.0
        if len(inflows) >= 14:
            previous = mean(inflows[-14:-7])
            recent = mean(inflows[-7:])
            if previous > 0:
                trend_factor = max(0.60, min(1.0, recent / previous))
        conservative_inflow = min(p20_inflow, median_inflow * 0.85) * trend_factor
        stressed_outflow = max(p80_outflow, recent_outflow)
    else:
        p20_inflow = median_inflow = p80_outflow = conservative_inflow = stressed_outflow = 0.0

    if req.cashflow_scope == "upi_only":
        risk_flags.append("UPI-only visibility may omit cash, card, other-app collections and off-platform expenses.")

    # Buffer covers at least two days of stressed operating expenses plus a shortfall
    # reserve when expected incoming money is below the stressed outflow run-rate.
    minimum_buffer = 5_000.0
    calculated_buffer = max(
        minimum_buffer,
        2.0 * stressed_outflow,
        stressed_outflow + 2.0 * max(0.0, stressed_outflow - conservative_inflow),
    )
    if req.seasonality_mode == "festive_surge":
        calculated_buffer *= 1.15
        risk_flags.append("Festive/seasonal mode adds 15% to the operating buffer.")
    elif req.seasonality_mode == "crunch_warning":
        calculated_buffer *= 1.35
        risk_flags.append("Cash-crunch stress mode adds 35% to the operating buffer.")
    if req.custom_buffer_override is not None:
        calculated_buffer = max(calculated_buffer, req.custom_buffer_override)
        if req.custom_buffer_override > 0:
            reasoning.append("Merchant buffer override was accepted only when it increased the protected floor.")
    working_buffer = _ceil_to(calculated_buffer)

    liability_schedule = _scheduled_liabilities(req)
    buckets = {"0_3": 0.0, "4_7": 0.0, "8_14": 0.0, "15_30": 0.0}
    for day, amount in liability_schedule.items():
        if day <= 3:
            buckets["0_3"] += amount
        elif day <= 7:
            buckets["4_7"] += amount
        elif day <= 14:
            buckets["8_14"] += amount
        else:
            buckets["15_30"] += amount
    total_liabilities = sum(buckets.values())

    forecast: list[ForecastDay] = []
    projected_balance = float(req.available_balance)
    min_projected_balance = projected_balance
    today = date.today()
    for day in range(1, req.horizon_days + 1):
        due = liability_schedule.get(day, 0.0)
        projected_balance += conservative_inflow - stressed_outflow - due
        min_projected_balance = min(min_projected_balance, projected_balance)
        forecast.append(
            ForecastDay(
                day=day,
                date=(today + timedelta(days=day)).isoformat(),
                conservative_inflow=round(conservative_inflow, 2),
                stressed_operating_outflow=round(stressed_outflow, 2),
                due_liabilities=round(due, 2),
                projected_closing_balance=round(projected_balance, 2),
            )
        )

    safe_surplus = max(0.0, min_projected_balance - working_buffer)
    data_quality = 100
    if freshness_grade == "DEGRADED_STALE":
        data_quality -= 25
    elif freshness_grade == "UNRELIABLE_HALT":
        data_quality -= 65
    if history_days < 14:
        data_quality -= 15
    if req.cashflow_scope == "upi_only":
        data_quality -= 15
    data_quality = max(0, min(100, data_quality))

    # A probability is deliberately not claimed. The band is a planning range from
    # conservative vs. median input assumptions, not a statistical confidence interval.
    typical_balance = float(req.available_balance)
    typical_min_balance = typical_balance
    typical_inflow = median_inflow
    typical_outflow = float(np.median(outflows)) if outflows else 0.0
    for day in range(1, req.horizon_days + 1):
        typical_balance += typical_inflow - typical_outflow - liability_schedule.get(day, 0.0)
        typical_min_balance = min(typical_min_balance, typical_balance)
    typical_surplus = max(safe_surplus, typical_min_balance - working_buffer)
    uncertainty_band = f"₹{_floor_to(safe_surplus):,.0f} – ₹{_floor_to(typical_surplus):,.0f}"

    if freshness_grade == "UNRELIABLE_HALT":
        reserve_status = "DATA_STALE_HOLD"
        recommended = 0.0
        reasoning.append("Freshness gate: recommendation paused because required source data is unavailable or too old.")
    elif not history_usable:
        reserve_status = "DATA_INSUFFICIENT_HOLD"
        recommended = 0.0
        reasoning.append("History gate: insufficient or outdated transaction history; no reserve recommendation is issued.")
    elif safe_surplus < 1_000:
        reserve_status = "PAUSE_RECOMMENDED"
        recommended = 0.0
        reasoning.append(f"Liquidity gate: minimum forecast balance ₹{min_projected_balance:,.0f} does not exceed the protected buffer ₹{working_buffer:,.0f} by enough to reserve.")
    else:
        reserve_ratio = 0.60 if safe_surplus < 10_000 else 0.70
        reserve_ratio *= freshness_factor
        if data_quality < 70:
            reserve_ratio *= 0.50
        recommended = _floor_to(safe_surplus * reserve_ratio)
        if recommended < 500:
            recommended = 0.0
        reserve_status = "CAUTIOUS_RESERVE" if (freshness_grade == "DEGRADED_STALE" or data_quality < 85 or safe_surplus < 10_000) else "READY_TO_RESERVE"
        reasoning.append(f"Liquidity forecast: lowest projected closing balance is ₹{min_projected_balance:,.0f} over {req.horizon_days} days.")
        reasoning.append(f"Protected floor: ₹{working_buffer:,.0f}; conservative safe surplus: ₹{safe_surplus:,.0f}.")
        reasoning.append(f"Reserve cap: {reserve_ratio:.0%} of safe surplus, rounded down to the nearest ₹100.")

    explanation = (
        f"Starting from ₹{req.available_balance:,.0f}, the conservative forecast reaches a low of "
        f"₹{min_projected_balance:,.0f} over {req.horizon_days} days after estimated routine outflows "
        f"and scheduled liabilities. MicroSave protects ₹{working_buffer:,.0f} as operating cash. "
        f"The resulting safe surplus is ₹{safe_surplus:,.0f}; the current recommendation is ₹{recommended:,.0f}."
    )
    if req.cashflow_scope == "upi_only":
        explanation += " This is a demo estimate based on UPI-visible collections and declared expenses; it may not represent the merchant's complete financial position."

    return SafeToReserveResponse(
        generated_at=generated_at,
        merchant_id=req.merchant_id,
        freshness_grade=freshness_grade,
        max_stale_minutes=max_stale,
        data_quality_score=data_quality,
        history_days=history_days,
        due_0_to_3_days=round(buckets["0_3"], 2),
        due_4_to_7_days=round(buckets["4_7"], 2),
        due_8_to_14_days=round(buckets["8_14"], 2),
        due_15_to_30_days=round(buckets["15_30"], 2),
        total_horizon_liabilities=round(total_liabilities, 2),
        available_balance=round(req.available_balance, 2),
        p20_daily_inflow=round(conservative_inflow, 2),
        p80_daily_operating_outflow=round(stressed_outflow, 2),
        working_capital_buffer=round(working_buffer, 2),
        projected_min_balance=round(min_projected_balance, 2),
        safe_surplus=round(safe_surplus, 2),
        recommended_reserve=round(recommended, 2),
        reserve_status=reserve_status,
        uncertainty_band=uncertainty_band,
        risk_flags=risk_flags,
        calibration_factors=[
            f"Conservative inflow: {p20_inflow:,.0f} P20 percentile, trend-adjusted to ₹{conservative_inflow:,.0f}/day.",
            f"Stressed routine outflow: ₹{stressed_outflow:,.0f}/day (max of P80 and latest 7-day average).",
            f"Protected buffer: max of ₹5,000 floor, two stressed operating days, and inflow/outflow shortfall reserve.",
        ],
        reasoning_steps=reasoning,
        decision_explanation=explanation,
        forecast=forecast,
    )
