"""Monitoring Worker — equipment monitoring training module.

This function is spawned in parallel by the workflow's dynamic fan-out task.
One instance runs per batch of monitoring rules dispatched by the orchestrator.

  POST /check_rules
    ├─ Accepts a list of {rule_external_id, time_series_external_id} check items
    ├─ Makes ONE batched CDF data.retrieve() call — server computes hourly
    │  aggregates (average, continuous_variance, max) over the last 24 hours
    │  That's 24 data points per series, never 86 400 raw datapoints
    ├─ Applies spike detection: breached when max > mean + 3σ
    └─ Returns {"results": [{rule_external_id, breached, mean_value, std_value,
                              max_value, status}, ...]}

  GET /health
    └─ Returns {"status": "ok"}

Spike detection algorithm
─────────────────────────
  mean = average of the 24 hourly averages
  std  = √(average of the 24 hourly continuous_variance values)
           (or std of the averages when variance is unavailable)
  max  = maximum of the 24 hourly maxima

  breached = max > mean + 3 × std

Server-side aggregation: CDF computes the statistics — the worker never
fetches raw datapoints.  Querying 100 time series × 24 h is a single API call
that returns 100 × 24 = 2 400 aggregate values instead of up to 8 640 000 raws.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np
from cognite.client import CogniteClient
from cognite_function_apps import FunctionApp
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FunctionApp(title="Monitoring Worker", version="2.0.0")


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------
class CheckItem(BaseModel):
    rule_external_id: str = Field(description="External ID of the MonitoringRule node")
    time_series_external_id: str = Field(description="CDF time series to fetch aggregates for")


class CheckResult(BaseModel):
    rule_external_id: str
    time_series_external_id: str
    breached: bool
    mean_value: float | None = None
    std_value: float | None = None
    max_value: float | None = None
    status: str = Field(description="'ok' | 'no_data' | 'error'")
    error: str | None = None


class BatchCheckRequest(BaseModel):
    checks: list[CheckItem] = Field(description="Rules to evaluate in this batch")


class BatchCheckResponse(BaseModel):
    results: list[CheckResult]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.post("/check_rules")
def check_rules(
    client: CogniteClient,
    logger: logging.Logger,
    body: BatchCheckRequest,
) -> BatchCheckResponse:
    """Run spike detection for a batch of monitoring rules.

    Makes ONE batched CDF data.retrieve() call with server-side hourly aggregates
    (24 points per series over 24 h) — never fetches raw datapoints.

    Spike condition: max > mean + 3σ
    """
    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=24)

    unique_eids = list({c.time_series_external_id for c in body.checks})
    logger.info(f"check_rules: {len(body.checks)} rules, {len(unique_eids)} unique time series")

    # ONE batched API call — server computes hourly stats (24 points, not 86 400 raw)
    aggregates_map: dict[str, Any] = {}
    if unique_eids:
        try:
            agg_data_list = client.time_series.data.retrieve(
                external_id=unique_eids,
                start=start,
                end=now,
                aggregates=["average", "continuous_variance", "max"],
                granularity="1h",
            )
            # retrieve() returns a DatapointsList when multiple external_ids are given
            items = agg_data_list if hasattr(agg_data_list, "__iter__") else [agg_data_list]
            for agg in items:
                if agg and agg.external_id:
                    aggregates_map[agg.external_id] = agg
        except Exception as exc:
            logger.error(f"Batch retrieve failed: {exc}")

    results = []
    for check in body.checks:
        agg = aggregates_map.get(check.time_series_external_id)
        if not agg or not agg.average:
            logger.debug(f"Rule {check.rule_external_id!r}: no data for {check.time_series_external_id!r}")
            results.append(CheckResult(
                rule_external_id=check.rule_external_id,
                time_series_external_id=check.time_series_external_id,
                breached=False,
                status="no_data",
            ))
            continue

        try:
            avg_vals = np.array([v for v in agg.average if v is not None], dtype=float)
            var_vals = np.array([v for v in agg.continuous_variance if v is not None], dtype=float)
            max_vals = np.array([v for v in agg.max if v is not None], dtype=float)

            if len(avg_vals) == 0:
                results.append(CheckResult(
                    rule_external_id=check.rule_external_id,
                    time_series_external_id=check.time_series_external_id,
                    breached=False,
                    status="no_data",
                ))
                continue

            mean = float(np.mean(avg_vals))
            std = float(np.sqrt(np.mean(var_vals))) if len(var_vals) > 0 else float(np.std(avg_vals))
            mx = float(np.max(max_vals)) if len(max_vals) > 0 else mean

            breached = mx > mean + 3 * std

            logger.info(
                f"Rule {check.rule_external_id!r} ({check.time_series_external_id!r}): "
                f"mean={mean:.2f} std={std:.2f} max={mx:.2f} breached={breached}"
            )

            results.append(CheckResult(
                rule_external_id=check.rule_external_id,
                time_series_external_id=check.time_series_external_id,
                breached=breached,
                mean_value=mean,
                std_value=std,
                max_value=mx,
                status="ok",
            ))

        except Exception as exc:
            logger.error(f"Rule {check.rule_external_id!r}: computation error: {exc}")
            results.append(CheckResult(
                rule_external_id=check.rule_external_id,
                time_series_external_id=check.time_series_external_id,
                breached=False,
                status="error",
                error=str(exc),
            ))

    breached_count = sum(1 for r in results if r.breached)
    logger.info(f"check_rules complete: {breached_count}/{len(results)} breached")

    return BatchCheckResponse(results=results)


@app.get("/health")
def health() -> dict[str, str]:
    """Smoke-test endpoint — returns OK if the function is running."""
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# CDF Functions entry point
# ---------------------------------------------------------------------------
def handle(data: dict, client: CogniteClient, secrets: dict | None = None, **_: Any) -> Any:
    """Entry point invoked by the CDF Functions runtime."""
    return app.handle(data, client)
