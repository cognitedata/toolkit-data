# Equipment Monitoring Training Module

A hands-on training module that demonstrates CDF patterns for equipment monitoring using Open Industrial Data (Valhall).

## What This Module Demonstrates

- **Dynamic worker pattern**: 1 workflow spawns N parallel workers at runtime (much faster than sequential)
- **cognite-function-apps**: FastAPI-style typed functions (orchestrator + worker)
- **`functionApp` task type**: New CDF Workflow capability replacing the old `function` type
- **Full data model**: Asset, Equipment, MonitoringRule, MonitoringRun
- **Queue pattern**: MonitoringRun DM nodes as work queue (`runStatus` tracking) + Records & Streams for alert output
- **Managed as code** with Toolkit: 2 functions, 1 workflow, 2 schedule triggers + 1 DM trigger

## Architecture

```
Two schedule triggers (hourly + nightly) → CDF Workflow:
  Task 1: functionApp → orchestrator POST /dispatch_workers
          Reads MonitoringRun nodes with runStatus=NotStarted
          Returns: list of N task defs + batch_id
  Task 2: dynamic
          Fans out N parallel tasks, each:
            functionApp → worker POST /check_threshold
            (fetches OID time series aggregate, compares to threshold)
  Task 3: functionApp → orchestrator POST /collect
          Aggregates results → updates MonitoringRun.runStatus
          Writes alert Records to Stream when threshold breached

DM Trigger (event-driven):
  Fires when new MonitoringRun nodes with runStatus=NotStarted appear
  Useful for testing/manual execution outside schedules
```

## Data Model

Four views in the `sp_equipment_monitoring` space:

| View | Purpose |
|------|---------|
| **Asset** | A monitored asset (e.g., pump, sensor) |
| **Equipment** | Equipment class grouping multiple assets |
| **MonitoringRule** | Defines what to check (time series, threshold, operator) |
| **MonitoringRun** | One execution of a rule against an asset (the work queue) |

### MonitoringRule properties

| Property | Type | Description |
|----------|------|-------------|
| `name` | text | Human-readable name |
| `description` | text | Rule description |
| `alarm_type` | text | Type of alarm (e.g., `"threshold"`) |
| `agent_name` | text | Worker route to call (e.g., `"check_threshold"`) |
| `time_series_external_id` | text | OID time series external ID |
| `threshold` | float64 | The threshold value |
| `threshold_operator` | text | `"gt"` (greater than) or `"lt"` (less than) |
| `equipment` | direct relation | Equipment class this rule applies to |

### MonitoringRun properties

| Property | Type | Description |
|----------|------|-------------|
| `name` | text | Human-readable name |
| `runStatus` | text | `NotStarted` → `InProgress` → `Completed` / `Failed` |
| `monitoringRunTS` | timestamp | Scheduled time for this run |
| `monitoringRule` | direct relation | The rule to execute |
| `asset` | direct relation | The asset to check |
| `result_message` | text | Output message from worker |

## Seed Data (OID Valhall tags)

Pre-configured MonitoringRule instances pointing to real Valhall time series:

| Tag | Description | Threshold | Operator |
|-----|-------------|-----------|----------|
| `VAL-23-PT-92504:X.Value` | Pump A suction pressure | 120 bar | gt |
| `VAL-23-FT-92537:X.Value` | Flow transmitter | 5 | lt |
| `VAL-23-TT-92508:X.Value` | Temperature sensor | 80°C | gt |

## Getting Started

1. Add this module to your `cdf.toml`:
   ```toml
   [library.training]
   url = "https://github.com/cognitedata/toolkit-data/blob/main/modules/packages.toml"
   ```

2. Select the module:
   ```bash
   cdf modules add
   # → Training > Equipment Monitoring
   ```

3. Deploy:
   ```bash
   cdf deploy
   ```

4. Seed MonitoringRun nodes in CDF (e.g., via the DM UI or a script) with `runStatus=NotStarted`

5. Trigger the workflow manually in CDF UI or wait for the hourly schedule

6. Observe:
   - N parallel `functionApp` tasks fanning out in the workflow execution view
   - MonitoringRun nodes updating from `NotStarted` → `InProgress` → `Completed`
   - Alert records in the `equipment_monitoring_alerts` stream (when thresholds are breached)

## Files

```
equipment_monitoring/
├── module.toml                          Module metadata
├── default.config.yaml                  Default configuration values
├── data_models/                         CDF Data Model definitions
│   ├── sp_equipment_monitoring.Space.yaml
│   ├── monitoring_solution.DataModel.yaml
│   ├── containers/                      Container schemas
│   └── views/                           View definitions
├── workflows/                           CDF Workflow + triggers
│   ├── monitoring.Workflow.yaml
│   ├── v1.WorkflowVersion.yaml          functionApp + dynamic tasks
│   ├── hourly.WorkflowTrigger.yaml      Runs every hour
│   ├── nightly.WorkflowTrigger.yaml     Runs at 02:00 UTC
│   └── dm_change.WorkflowTrigger.yaml   Event-driven via DM change
├── functions/                           CDF Functions
│   ├── orchestrator.Function.yaml
│   ├── fn_monitoring_orchestrator/      Orchestrator code
│   ├── worker.Function.yaml
│   └── fn_monitoring_worker/            Worker code
├── streams/
│   └── monitoring_alerts.Streams.yaml   Alert output stream
└── auth/
    └── monitoring.Group.yaml            CDF Group with capabilities
```
