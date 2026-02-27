"""Monitoring Seeder — equipment monitoring training module.

Runs as Task 0 of every workflow execution, keeping synthetic compressor time
series data fresh so the monitoring worker always has data in its 24-hour window.

  POST /seed_tick
    ├─ Creates the 3 compressor TS resources in CDF if they do not exist yet
    ├─ First run (no data in last 24 h): backfills 168 hourly datapoints (7 days)
    │  with a spike injected at mean + 4.5σ every ~50 hours
    ├─ Subsequent runs: appends one new datapoint at now()
    │  (Gaussian noise + 5 % random spike chance)
    └─ Returns {"ticked": int, "backfilled": bool}

  GET /health
    └─ Returns {"status": "ok"}

Compressor signals
──────────────────
  comp_lp_flow             LP Compressor Suction Flow    mean=1200 std=80  unit=m3/h
  comp_hp_flow             HP Compressor Suction Flow    mean=800  std=60  unit=m3/h
  comp_recirculation_flow  Recirculation Flow            mean=300  std=30  unit=m3/h

These are the same external IDs used by the seed MonitoringRule DM nodes (see
the README for how to upsert the seed rules via `cdf deploy`).

Educational aside — CDF Synthetic TS for surge margin
──────────────────────────────────────────────────────
CDF can compute derived metrics on-the-fly, without storing them:

  from cognite.client.data_classes import SyntheticDatapointQuery

  results = client.time_series.synthetic.query(
      expressions=[
          SyntheticDatapointQuery(
              expression="(ts{externalId='comp_lp_flow'} - 950) / 950 * 100",
              id="lp_surge_margin_pct",
          )
      ],
      start=now - timedelta(hours=24),
      end=now,
      limit=10_000,
  )

The monitoring worker uses the *smart aggregation* path (stored TS with
server-side stats), while this synthetic TS pattern illustrates how derived
metrics can be built without additional storage or ETL pipelines.
"""

import logging
import random
from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np
from cognite.client import CogniteClient
from cognite.client.data_classes import TimeSeries
from cognite.client.exceptions import CogniteAPIError
from cognite_function_apps import FunctionApp

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
COMP_CONFIG = [
    {"eid": "comp_lp_flow",            "name": "LP Compressor Suction Flow",  "unit": "m3/h", "mean": 1200.0, "std": 80.0},
    {"eid": "comp_hp_flow",            "name": "HP Compressor Suction Flow",  "unit": "m3/h", "mean": 800.0,  "std": 60.0},
    {"eid": "comp_recirculation_flow", "name": "Recirculation Flow",          "unit": "m3/h", "mean": 300.0,  "std": 30.0},
]

LOOKBACK_HOURS = 24    # window the worker checks
BACKFILL_HOURS = 7 * 24  # 7 days of history on first run
SPIKE_INTERVAL_HOURS = 50  # inject a spike every ~50 hours in backfill

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FunctionApp(title="Monitoring Seeder", version="1.0.0")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ensure_time_series(client: CogniteClient, logger: logging.Logger) -> None:
    """Create compressor TS resources if they do not exist yet."""
    existing_eids: set[str] = set()
    try:
        existing = client.time_series.retrieve_multiple(
            external_ids=[c["eid"] for c in COMP_CONFIG],
            ignore_unknown_ids=True,
        )
        existing_eids = {ts.external_id for ts in existing if ts}
    except Exception as exc:
        logger.warning(f"Could not check existing time series: {exc}")

    to_create = [
        TimeSeries(
            external_id=c["eid"],
            name=c["name"],
            unit=c["unit"],
            is_step=False,
            description="Synthetic compressor signal for equipment monitoring demo",
        )
        for c in COMP_CONFIG
        if c["eid"] not in existing_eids
    ]
    if to_create:
        client.time_series.create(to_create)
        logger.info(f"Created {len(to_create)} time series: {[ts.external_id for ts in to_create]}")


def _has_recent_data(client: CogniteClient, eid: str) -> bool:
    """Return True if the TS has at least one datapoint in the last LOOKBACK_HOURS."""
    now = datetime.now(timezone.utc)
    try:
        dps = client.time_series.data.retrieve(
            external_id=eid,
            start=now - timedelta(hours=LOOKBACK_HOURS),
            end=now,
            limit=1,
        )
        return bool(dps and len(dps) > 0)
    except Exception:
        return False


def _backfill(client: CogniteClient, logger: logging.Logger, cfg: dict[str, Any], now: datetime) -> None:
    """Insert BACKFILL_HOURS hourly datapoints ending at now, with injected spikes."""
    rng = np.random.default_rng(seed=abs(hash(cfg["eid"])) % (2**32))
    timestamps = [now - timedelta(hours=BACKFILL_HOURS - h) for h in range(BACKFILL_HOURS)]
    values = rng.normal(cfg["mean"], cfg["std"], size=BACKFILL_HOURS).tolist()

    # Inject a spike at mean + 4.5σ every SPIKE_INTERVAL_HOURS
    for i in range(0, BACKFILL_HOURS, SPIKE_INTERVAL_HOURS):
        values[i] = cfg["mean"] + 4.5 * cfg["std"]

    client.time_series.data.insert(datapoints=list(zip(timestamps, values)), external_id=cfg["eid"])
    logger.info(f"Backfilled {len(values)} points for {cfg['eid']!r}")


def _tick(client: CogniteClient, logger: logging.Logger, cfg: dict[str, Any], now: datetime) -> None:
    """Append one new datapoint at now: Gaussian noise with a 5 % spike chance."""
    if random.random() < 0.05:  # noqa: S311
        value = cfg["mean"] + 4.5 * cfg["std"]
        logger.info(f"Spike tick for {cfg['eid']!r}: {value:.1f}")
    else:
        value = float(np.random.normal(cfg["mean"], cfg["std"]))
    client.time_series.data.insert(datapoints=[(now, value)], external_id=cfg["eid"])


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.post("/seed_tick")
def seed_tick(
    client: CogniteClient,
    logger: logging.Logger,
) -> dict[str, Any]:
    """Backfill on first run; append one datapoint on every subsequent run."""
    now = datetime.now(timezone.utc)
    _ensure_time_series(client, logger)

    ticked = 0
    backfilled = False

    for cfg in COMP_CONFIG:
        try:
            if not _has_recent_data(client, cfg["eid"]):
                logger.info(f"{cfg['eid']!r}: no recent data — running backfill")
                _backfill(client, logger, cfg, now)
                backfilled = True
            else:
                _tick(client, logger, cfg, now)
            ticked += 1
        except CogniteAPIError as exc:
            logger.error(f"CDF API error for {cfg['eid']!r}: {exc}")
        except Exception as exc:
            logger.error(f"Unexpected error for {cfg['eid']!r}: {exc}")

    logger.info(f"seed_tick complete: ticked={ticked}, backfilled={backfilled}")
    return {"ticked": ticked, "backfilled": backfilled}


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
