from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from core.connectors.base import (
    SourceConnector,
    TargetConnector,
    CDCEngine,
    Schema,
    Column,
    UpsertResult,
    ApplyResult,
    ChangeEvent,
    validate_identifier,
)
from core.driver_installer import ensure_driver
from core.retry import retry_with_backoff
from core.audit_logger import audit_log


class MySQLSourceConnector(SourceConnector):
    def __init__(self, config: dict[str, Any]) -> None:
        self._config = config
        self._conn: Any = None

    @retry_with_backoff(max_retries=3, base_delay=1.0)
    def connect(self) -> None:
        ensure_driver("mysql-connector-python", "mysql.connector")
        import mysql.connector

        conn_kwargs: dict[str, Any] = {
            "host": self._config["host"],
            "port": self._config.get("port", 3306),
            "database": self._config["database"],
            "user": self._config["username"],
            "password": self._config.get("password", ""),
            "ssl_disabled": not self._config.get("ssl", True),
        }

        self._conn = mysql.connector.connect(**conn_kwargs)
        audit_log(phase="connect", status="success", details={"engine": "mysql", "role": "source"})

    def list_objects(self) -> list[str]:
        db_name = self._config["database"]
        validate_identifier(db_name, "database")
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES "
                "WHERE TABLE_SCHEMA = %s AND TABLE_TYPE = 'BASE TABLE'",
                (db_name,),
            )
            tables = [row[0] for row in cur.fetchall()]
        for t in tables:
            validate_identifier(t, "table")
        return tables

    def get_object_count(self, object_name: str) -> int:
        validate_identifier(object_name, "table")
        with self._conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM {object_name}")
            return cur.fetchone()[0]

    def export_full(self, object_name: str) -> Iterator[dict[str, Any]]:
        validate_identifier(object_name, "table")
        with self._conn.cursor(dictionary=True) as cur:
            cur.execute(f"SELECT * FROM {object_name}")
            for row in cur:
                yield dict(row)

    def get_schema(self, object_name: str) -> Schema:
        validate_identifier(object_name, "table")
        columns: list[Column] = []
        primary_key: list[str] = []

        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, CHARACTER_MAXIMUM_LENGTH "
                "FROM INFORMATION_SCHEMA.COLUMNS "
                "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s "
                "ORDER BY ORDINAL_POSITION",
                (self._config["database"], object_name),
            )
            for row in cur.fetchall():
                col_name, data_type, nullable, max_len = row
                columns.append(
                    Column(
                        name=col_name,
                        source_type=data_type,
                        target_type=None,
                        nullable=(nullable == "YES"),
                        size=max_len,
                    )
                )

            cur.execute(
                "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE "
                "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s "
                "AND CONSTRAINT_NAME = 'PRIMARY'",
                (self._config["database"], object_name),
            )
            primary_key = [row[0] for row in cur.fetchall()]

        return Schema(name=object_name, columns=columns, primary_key=primary_key)


class MySQLTargetConnector(TargetConnector):
    def __init__(self, config: dict[str, Any]) -> None:
        self._config = config
        self._conn: Any = None

    @retry_with_backoff(max_retries=3, base_delay=1.0)
    def connect(self) -> None:
        ensure_driver("mysql-connector-python", "mysql.connector")
        import mysql.connector

        conn_kwargs: dict[str, Any] = {
            "host": self._config["host"],
            "port": self._config.get("port", 3306),
            "database": self._config.get("database", "mysql"),
            "user": self._config["username"],
            "password": self._config.get("password", ""),
            "ssl_disabled": not self._config.get("ssl", True),
        }

        self._conn = mysql.connector.connect(**conn_kwargs)
        audit_log(phase="connect", status="success", details={"engine": "mysql", "role": "target"})

    def ensure_database_exists(self) -> None:
        db_name = self._config["database"]
        validate_identifier(db_name, "database")
        with self._conn.cursor() as cur:
            cur.execute("SELECT SCHEMA_NAME FROM INFORMATION_SCHEMA.SCHEMATA WHERE SCHEMA_NAME = %s", (db_name,))
            if cur.fetchone() is None:
                cur.execute(f"CREATE DATABASE {db_name}")
                audit_log(phase="ensure_database", status="created", details={"database": db_name})

    def create_object_if_missing(self, schema: Schema) -> None:
        validate_identifier(schema.name, "table")
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES "
                "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s",
                (self._config.get("database", "mysql"), schema.name),
            )
            if cur.fetchone() is not None:
                return

            col_defs = []
            for col in schema.columns:
                col_type = col.target_type or col.source_type
                null_str = "NULL" if col.nullable else "NOT NULL"
                col_defs.append(f"{col.name} {col_type} {null_str}")

            if schema.primary_key:
                pk_cols = ", ".join(schema.primary_key)
                col_defs.append(f"PRIMARY KEY ({pk_cols})")

            ddl = f"CREATE TABLE {schema.name} ({', '.join(col_defs)})"
            cur.execute(ddl)
            self._conn.commit()
            audit_log(phase="create_table", status="created", details={"table": schema.name})

    def upsert_batch(self, object_name: str, rows: Iterator[dict[str, Any]], schema: Schema | None = None) -> UpsertResult:
        validate_identifier(object_name, "table")
        result = UpsertResult()
        batch = list(rows)

        if not batch:
            return result

        with self._conn.cursor() as cur:
            columns = list(batch[0].keys())
            col_names = ", ".join(columns)
            placeholders = ", ".join(["%s"] * len(columns))
            update_set = ", ".join(
                f"{col} = VALUES({col})" for col in columns
            )

            sql = (
                f"INSERT INTO {object_name} ({col_names}) "
                f"VALUES ({placeholders}) "
                f"ON DUPLICATE KEY UPDATE {update_set}"
            )

            try:
                for row in batch:
                    values = [row.get(col) for col in columns]
                    cur.execute(sql, values)
                self._conn.commit()
                result.success_count = len(batch)
                audit_log(phase="upsert_batch", status="success", details={"table": object_name, "count": len(batch)})
            except Exception as exc:
                self._conn.rollback()
                result.failure_count = len(batch)
                result.errors.append(str(exc))
                result.failed_items.extend(batch)
                audit_log(phase="upsert_batch", status="failure", details={"table": object_name, "error": str(exc)})

        return result

    def get_object_count(self, object_name: str) -> int:
        validate_identifier(object_name, "table")
        with self._conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM {object_name}")
            return cur.fetchone()[0]

    def delete(self, object_name: str, document: dict[str, Any], schema: Schema | None = None) -> None:
        validate_identifier(object_name, "table")
        with self._conn.cursor() as cur:
            if schema and schema.primary_key:
                conditions = []
                values = []
                for pk_col in schema.primary_key:
                    conditions.append(f"{pk_col} = %s")
                    values.append(document.get(pk_col))
                where_clause = " AND ".join(conditions)
                cur.execute(f"DELETE FROM {object_name} WHERE {where_clause}", values)
            else:
                cur.execute(f"DELETE FROM {object_name} WHERE id = %s", (document.get("id"),))
            self._conn.commit()
            audit_log(phase="cdc_delete", status="deleted", details={"table": object_name})

    def export_full(self, object_name: str) -> Iterator[dict[str, Any]]:
        validate_identifier(object_name, "table")
        with self._conn.cursor(dictionary=True) as cur:
            cur.execute(f"SELECT * FROM {object_name}")
            for row in cur:
                yield dict(row)


class MySQLCDCEngine(CDCEngine):
    def __init__(self, config: dict[str, Any]) -> None:
        self._config = config
        self._conn: Any = None
        self._last_binlog_file: str | None = None
        self._last_binlog_pos: int | None = None

    @retry_with_backoff(max_retries=3, base_delay=1.0)
    def connect(self) -> None:
        import mysql.connector

        conn_kwargs: dict[str, Any] = {
            "host": self._config["host"],
            "port": self._config.get("port", 3306),
            "database": self._config["database"],
            "user": self._config["username"],
            "password": self._config.get("password", ""),
            "ssl_disabled": not self._config.get("ssl", True),
        }

        self._conn = mysql.connector.connect(**conn_kwargs)

    def start(self) -> None:
        with self._conn.cursor() as cur:
            cur.execute("SHOW MASTER STATUS")
            row = cur.fetchone()
            if row:
                self._last_binlog_file = row[0]
                self._last_binlog_pos = row[1]
        audit_log(phase="cdc_start", status="success", details={"engine": "mysql"})

    def poll_changes(self) -> list[ChangeEvent]:
        from pymysqlreplication import BinlogStreamReader
        from pymysqlreplication.row_event import (
            WriteRowsEvent,
            UpdateRowsEvent,
            DeleteRowsEvent,
        )

        conn_kwargs: dict[str, Any] = {
            "host": self._config["host"],
            "port": self._config.get("port", 3306),
            "user": self._config["username"],
            "passwd": self._config.get("password", ""),
            "ssl": self._config.get("ssl", True),
            "connect_timeout": 5,
            "read_timeout": 5,
        }

        stream = BinlogStreamReader(
            connection_settings=conn_kwargs,
            server_id=self._config.get("server_id", 100),
            blocking=False,
            resume_stream=self._last_binlog_file is not None,
            log_file=self._last_binlog_file,
            log_pos=self._last_binlog_pos or 4,
            only_events=[WriteRowsEvent, UpdateRowsEvent, DeleteRowsEvent],
        )

        events: list[ChangeEvent] = []
        try:
            for binlogevent in stream:
                if isinstance(binlogevent, WriteRowsEvent):
                    operation = "insert"
                    for row in binlogevent.rows:
                        document = row["values"]
                        events.append(
                            ChangeEvent(
                                operation=operation,
                                document=document,
                                object_name=binlogevent.table,
                                watermark={
                                    "file": binlogevent.log_file,
                                    "pos": binlogevent.log_pos,
                                },
                            )
                        )
                elif isinstance(binlogevent, UpdateRowsEvent):
                    operation = "update"
                    for row in binlogevent.rows:
                        document = row["after_values"]
                        events.append(
                            ChangeEvent(
                                operation=operation,
                                document=document,
                                object_name=binlogevent.table,
                                watermark={
                                    "file": binlogevent.log_file,
                                    "pos": binlogevent.log_pos,
                                },
                            )
                        )
                elif isinstance(binlogevent, DeleteRowsEvent):
                    operation = "delete"
                    for row in binlogevent.rows:
                        document = row["values"]
                        events.append(
                            ChangeEvent(
                                operation=operation,
                                document=document,
                                object_name=binlogevent.table,
                                watermark={
                                    "file": binlogevent.log_file,
                                    "pos": binlogevent.log_pos,
                                },
                            )
                        )
        finally:
            stream.close()

        return events

    def apply(self, events: list[ChangeEvent], target: TargetConnector) -> ApplyResult:
        result = ApplyResult()
        if not events:
            return result

        for event in events:
            try:
                if event.operation == "insert":
                    target.upsert_batch(event.object_name, iter([event.document]), event.schema)
                elif event.operation == "update":
                    target.upsert_batch(event.object_name, iter([event.document]), event.schema)
                elif event.operation == "delete":
                    target.delete(event.object_name, event.document, event.schema)
                result.success_count += 1
            except Exception as exc:
                result.failure_count += 1
                result.errors.append(str(exc))

        if result.failure_count == 0:
            result.last_checkpoint = events[-1].watermark
            audit_log(phase="cdc_apply", status="success", details={"applied": result.success_count})
        else:
            audit_log(phase="cdc_apply", status="partial_failure", details={"success": result.success_count, "failure": result.failure_count})

        return result

    def checkpoint(self, result: ApplyResult) -> None:
        if result.last_checkpoint is None:
            return

        watermark = result.last_checkpoint
        if isinstance(watermark, dict):
            self._last_binlog_file = watermark.get("file")
            self._last_binlog_pos = watermark.get("pos")
        else:
            self._last_binlog_file = str(watermark)
            self._last_binlog_pos = None
        audit_log(phase="cdc_checkpoint", status="advanced", details={"binlog_file": self._last_binlog_file, "binlog_pos": self._last_binlog_pos})
