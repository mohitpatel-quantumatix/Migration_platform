# Architecture — Unified Cross-Database Migration Platform

## Overview

The platform provides a unified, OS-independent, Docker-packaged system for migrating data between heterogeneous database engines. It supports PostgreSQL, MySQL, MongoDB, MSSQL, and Cosmos DB (MongoDB API) as source and target engines.

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   Migration Orchestrator                │
│  run_full() | run_cdc() | run_assessment() | validate()│
└──────────────┬──────────────────────────┬───────────────┘
               │                          │
    ┌──────────▼──────────┐  ┌───────────▼───────────┐
    │   SourceConnector   │  │   TargetConnector     │
    │   (engine-specific) │  │   (engine-specific)   │
    └──────────┬──────────┘  └───────────┬───────────┘
               │                          │
    ┌──────────▼──────────┐  ┌───────────▼───────────┐
    │   Schema Mapping    │  │   Schema Mapping      │
    │   TypeMapper        │  │   TypeMapper          │
    └─────────────────────┘  └───────────────────────┘
               │
    ┌──────────▼──────────┐
    │   TypeMappingRegistry│
    │   (config-driven)    │
    └─────────────────────┘

    ┌─────────────────────────────────────────────────┐
    │              Supporting Services                │
    │  Retry/Backoff | Audit Logger | Secrets Mgmt   │
    │  Alerting | Status Server | Validation         │
    └─────────────────────────────────────────────────┘
```

## Connector Interface Contracts

### SourceConnector
- `connect()` — Establishes connection to source database
- `list_objects()` — Returns list of object names (tables/collections)
- `get_object_count(object_name)` — Returns row/document count
- `export_full(object_name)` — Returns `Iterator[dict]` streaming rows/documents
- `get_schema(object_name)` — Returns `Schema` with columns, types, primary key

### TargetConnector
- `connect()` — Establishes connection to target database
- `ensure_database_exists()` — Creates database if it does not exist
- `create_object_if_missing(schema)` — Creates table/collection with mapped schema
- `upsert_batch(object_name, rows)` — Bulk upsert using engine-native merge syntax
- `get_object_count(object_name)` — Returns row/document count

### CDCEngine
- `start()` — Initializes change tracking (replication slot, oplog tailing, etc.)
- `poll_changes()` — Returns `list[ChangeEvent]` since last checkpoint
- `apply(events)` — Applies change events to target
- `checkpoint(events)` — Advances past successfully applied events only

## Data Flow

### Full Migration Mode
1. Orchestrator calls `source.connect()` and `target.connect()`
2. `source.list_objects()` discovers all source objects
3. For each object:
   a. `source.get_schema()` reads column definitions
   b. `TypeMappingRegistry.map_type()` translates types
   c. `target.create_object_if_missing()` creates target object
   d. `source.export_full()` streams rows
   e. `target.upsert_batch()` writes rows (INSERT ... ON CONFLICT / MERGE / bulk_write)
4. `Validator.validate_count()` compares source and target counts
5. Final status derived from validation results

### CDC Mode
1. Initial full sync (same as full migration)
2. CDC engine starts (replication slot / oplog / binlog / change feed)
3. Continuous polling of changes
4. Changes applied to target via `cdc_engine.apply()`
5. Checkpoint advanced only on full batch success

## Configuration Schema

The configuration is defined in `config/migration_config.schema.yaml` and validated at runtime using Cerberus. Key sections:

- `source` — Engine type, connection details, SSL settings
- `target` — Engine type, connection details, SSL settings
- `migration` — Mode (full/cdc), batch size, field mappings, size limits
- `retry` — Max retries, backoff delays, circuit breaker thresholds
- `secrets` — Provider type (env/azure_keyvault), vault URL
- `alerting` — Notifier type (webhook/slack/teams/email)
- `validation` — Mode (count/checksum/full), sample size

## Bug-Fix Constraints

The 11 bug classes from the predecessor system are encoded as explicit constraints:

| # | Constraint | Enforcement |
|---|-----------|-------------|
| 1 | Never combine DROP/truncate with incremental export | `upsert_batch` uses INSERT/ON CONFLICT/MERGE/bulk_write |
| 2 | Final status from validation, never hardcoded | Orchestrator derives status from validation result |
| 3 | Partial batch failure → no checkpoint advance | CDC checkpoint only advances on full batch success |
| 4 | Type-safe incremental queries (native driver types) | ObjectId comparisons use native ObjectId type |
| 5 | Object name validation against identifier regex | `validate_identifier()` called on all object names |
| 6 | No hardcoded secrets/IPs in code | All credentials from secret provider |
| 7 | Network rules additive, never replace | N/A in code (infra-level constraint) |
| 8 | One CDC implementation per engine | Single CDC class per connector module |
| 9 | URI encoding uses `quote`, not `quote_plus` | All connectors pass connection params as kwargs, not percent-encoded strings |
| 10 | TLS validation on by default | `sslmode=verify-full` (Postgres), `Encrypt=yes` (MSSQL), `tls=True` (Mongo) |
| 11 | Rate-limited bulk ops use exponential backoff | Cosmos connector uses `retry_with_backoff` with max_retries=5 |

## Security

- All credentials are resolved through the `SecretProvider` abstraction
- No secrets are stored in code or configuration files
- TLS is enabled by default for all connectors
- URI encoding uses `urllib.parse.quote` with `safe=""` to properly encode special characters
- Object name validation prevents SQL/NoSQL injection via identifier sanitization