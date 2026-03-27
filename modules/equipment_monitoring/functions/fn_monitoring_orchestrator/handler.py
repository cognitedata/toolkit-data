"""Monitoring Orchestrator — equipment monitoring training module.

Two routes, called by one CDF Workflow:

  POST /dispatch_workers                     ← Task 1 of the monitoring workflow
    ├─ Reads all MonitoringRule nodes matching interval_minutes from Data Modeling
    ├─ Groups them into batches of WORKER_BATCH_SIZE (100 rules per batch)
    ├─ Builds one functionApp task definition per batch (each batch = 1 CDF API call)
    └─ Returns {"tasks": [...], "batch_id": "<uuid>", "rule_count": N}

  POST /collect                              ← Task 3 of the monitoring workflow
    ├─ Receives the raw dynamic fan-out output (dict keyed by task externalId)
    ├─ Flattens each batch's results list
    ├─ Writes an alert Record to the monitoring_alerts Stream for every breached result
    └─ Returns {"batch_id": ..., "total_results": N, "alerts_written": M}

  GET /health
    └─ Returns {"status": "ok"} — used for smoke-testing after deploy

Key concepts demonstrated:
  - cognite-function-apps: FastAPI-style typed functions
  - Data Modeling: filter nodes by property value (interval_minutes)
  - Batch dispatch: N rules → ceil(N/100) worker tasks, each making 1 CDF API call
  - Smart aggregation: server-side hourly stats — no raw data ever fetched
  - Records & Streams for alert output
"""

import logging
import uuid
from typing import Any

from cognite.client import CogniteClient
from cognite.client.data_classes.data_modeling import ViewId, filters
from cognite_function_apps import FunctionApp
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Configuration — overridden by Toolkit template at deploy time
# ---------------------------------------------------------------------------
SPACE = "sp_equipment_monitoring"
WORKER_FUNCTION_EID = "fn_monitoring_worker"
ALERT_STREAM_EID = "equipment_monitoring_alerts"
WORKER_BATCH_SIZE = 100

MONITORING_RULE_VIEW = ViewId(SPACE, "MonitoringRule", "1.0")

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FunctionApp(title="Monitoring Orchestrator", version="2.0.0")


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------
class DispatchRequest(BaseModel):
    interval_minutes: int = Field(description="Only dispatch rules with this interval (e.g., 15 or 60)")


class DispatchResponse(BaseModel):
    tasks: list[dict[str, Any]] = Field(description="Dynamic task definitions for the workflow fan-out")
    batch_id: str = Field(description="Unique ID for this dispatch batch")
    rule_count: int = Field(description="Total number of MonitoringRule nodes dispatched")


class CollectRequest(BaseModel):
    batch_id: str
    worker_results: Any = Field(
        description="Raw dynamic fan-out output — dict keyed by worker task externalId"
    )


class CollectResponse(BaseModel):
    batch_id: str
    total_results: int
    alerts_written: int


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.post("/dispatch_workers")
def dispatch_workers(
    client: CogniteClient,
    logger: logging.Logger,
    body: DispatchRequest,
) -> DispatchResponse:
    """Filter MonitoringRules by interval_minutes, build one worker task per batch of 100.

    One DM list call fetches all matching rules (up to 10 000).  Rules are grouped
    into batches of WORKER_BATCH_SIZE; each batch becomes one dynamic task that
    calls /check_rules on the worker with a list of
    {rule_external_id, time_series_external_id} pairs.

    The worker makes exactly ONE batched CDF data.retrieve() call per batch —
    server-side hourly aggregates over 24 h (24 points, not 86 400 raw datapoints).
    """
    batch_id = str(uuid.uuid4())
    logger.info(f"dispatch_workers: interval_minutes={body.interval_minutes} batch_id={batch_id}")

    # One DM list call — filter rules by interval
    rule_nodes = client.data_modeling.instances.list(
        instance_type="node",
        sources=[MONITORING_RULE_VIEW],
        filter=filters.Equals(
            property=[SPACE, "MonitoringRule", "interval_minutes"],
            value=body.interval_minutes,
        ),
        limit=10_000,
    )
    logger.info(f"Found {len(rule_nodes)} MonitoringRule nodes for interval_minutes={body.interval_minutes}")

    checks = []
    for node in rule_nodes:
        props = _get_props(node, SPACE, "MonitoringRule", "1.0")
        ts_eid = props.get("time_series_external_id")
        if ts_eid:
            checks.append({
                "rule_external_id": node.external_id,
                "time_series_external_id": ts_eid,
            })
        else:
            logger.warning(f"Rule {node.external_id!r} has no time_series_external_id — skipping")

    # One worker task per batch of WORKER_BATCH_SIZE rules
    tasks: list[dict[str, Any]] = [
        {
            "externalId": f"worker-batch-{i}",
            "type": "functionApp",
            "input": {
                "functionApp": {
                    "externalId": WORKER_FUNCTION_EID,
                    "method": "POST",
                    "path": "/check_rules",
                    "body": {"checks": checks[i: i + WORKER_BATCH_SIZE]},
                }
            },
        }
        for i in range(0, max(len(checks), 1), WORKER_BATCH_SIZE)
    ]

    logger.info(
        f"Dispatching {len(tasks)} worker task(s) covering {len(checks)} rules (batch_id={batch_id})"
    )
    return DispatchResponse(tasks=tasks, batch_id=batch_id, rule_count=len(checks))


@app.post("/collect")
def collect(
    client: CogniteClient,
    logger: logging.Logger,
    body: CollectRequest,
) -> CollectResponse:
    """Flatten dynamic worker outputs; write breached alerts to the monitoring Stream.

    worker_results is the raw output of the dynamic fan-out task — a dict keyed by
    worker task externalId.  Each value is the direct return value of /check_rules,
    i.e. {"results": [{"rule_external_id": ..., "breached": bool, ...}, ...]}.
    """
    logger.info(f"collect: batch_id={body.batch_id}")

    all_results: list[dict[str, Any]] = []

    if isinstance(body.worker_results, dict):
        for task_id, task_out in body.worker_results.items():
            task_results = task_out.get("results", []) if isinstance(task_out, dict) else []
            logger.debug(f"Task {task_id}: {len(task_results)} result(s)")
            all_results.extend(task_results)
    elif isinstance(body.worker_results, list):
        for item in body.worker_results:
            if isinstance(item, dict):
                all_results.extend(item.get("results", []))

    alerts = [r for r in all_results if r.get("breached")]
    logger.info(f"collect: {len(all_results)} total results, {len(alerts)} breached")

    if alerts:
        client.streams.records.upsert(
            stream_external_id=ALERT_STREAM_EID,
            records=alerts,
        )
        logger.info(f"Wrote {len(alerts)} alert record(s) to stream {ALERT_STREAM_EID!r}")

    return CollectResponse(
        batch_id=body.batch_id,
        total_results=len(all_results),
        alerts_written=len(alerts),
    )


@app.get("/health")
def health() -> dict[str, str]:
    """Smoke-test endpoint — returns OK if the function is running."""
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_props(node: Any, space: str, view_eid: str, version: str) -> dict[str, Any]:
    """Extract the property dict for a given view from a node's properties."""
    try:
        return node.properties[space][f"{view_eid}/{version}"]
    except (KeyError, TypeError):
        return {}


# ---------------------------------------------------------------------------
# CDF Functions entry point
# ---------------------------------------------------------------------------
def handle(data: dict, client: CogniteClient, secrets: dict | None = None, **_: Any) -> Any:
    """Entry point invoked by the CDF Functions runtime."""
    return app.handle(data, client)
