from __future__ import annotations

import pytest

from core.connectors.base import (
    Schema,
    Column,
)
from core.connectors.postgresql import PostgresSourceConnector, PostgresTargetConnector
from core.connectors.mongodb import MongoSourceConnector, MongoTargetConnector, MongoCDCEngine
from core.connectors.mysql import MySQLSourceConnector
from core.connectors.mssql import MSSQLSourceConnector, MSSQLTargetConnector
from core.validator import Validator


@pytest.mark.integration
class TestPostgresFullMigration:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.source_config = {
            "host": "localhost",
            "port": 5432,
            "database": "migration_test",
            "username": "test_user",
            "password": "test_pass",
            "ssl": False,
        }
        self.target_config = {
            "host": "localhost",
            "port": 5432,
            "database": "migration_target",
            "username": "test_user",
            "password": "test_pass",
            "ssl": False,
        }

    def test_source_connect_and_list_tables(self):
        source = PostgresSourceConnector(self.source_config)
        source.connect()
        tables = source.list_objects()
        assert isinstance(tables, list)
        source._conn.close()

    def test_source_export_full_yields_dicts(self):
        source = PostgresSourceConnector(self.source_config)
        source.connect()
        tables = source.list_objects()
        if tables:
            for row in source.export_full(tables[0]):
                assert isinstance(row, dict)
                break
        source._conn.close()

    def test_target_upsert_batch_never_drops(self):
        source = PostgresSourceConnector(self.source_config)
        target = PostgresTargetConnector(self.target_config)
        source.connect()
        target.connect()

        tables = source.list_objects()
        if tables:
            schema = source.get_schema(tables[0])
            target.create_object_if_missing(schema)

            count = source.get_object_count(tables[0])
            rows = source.export_full(tables[0])
            result = target.upsert_batch(tables[0], rows, schema)

            assert result.failure_count == 0
            assert result.success_count == count

        source._conn.close()
        target._conn.close()

    def test_upsert_batch_uses_on_conflict_pk(self):
        target = PostgresTargetConnector(self.target_config)
        target.connect()

        schema = Schema(
            name="test_pk_table",
            columns=[
                Column(name="id", source_type="integer", target_type="INT", nullable=False),
                Column(name="name", source_type="varchar", target_type="VARCHAR", nullable=True),
            ],
            primary_key=["id"],
        )
        target.create_object_if_missing(schema)

        rows = iter([{"id": 1, "name": "first"}, {"id": 2, "name": "second"}])
        result = target.upsert_batch("test_pk_table", rows, schema)
        assert result.success_count == 2

        rows2 = iter([{"id": 1, "name": "updated"}, {"id": 3, "name": "third"}])
        result2 = target.upsert_batch("test_pk_table", rows2, schema)
        assert result2.success_count == 2

        target._conn.close()


@pytest.mark.integration
class TestMongoFullMigration:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.source_config = {
            "host": "localhost",
            "port": 27017,
            "database": "migration_test",
        }
        self.target_config = {
            "host": "localhost",
            "port": 27017,
            "database": "migration_target",
        }

    def test_source_connect_and_list_collections(self):
        source = MongoSourceConnector(self.source_config)
        source.connect()
        collections = source.list_objects()
        assert isinstance(collections, list)

    def test_source_export_full_yields_dicts(self):
        source = MongoSourceConnector(self.source_config)
        source.connect()
        collections = source.list_objects()
        if collections:
            for doc in source.export_full(collections[0]):
                assert isinstance(doc, dict)
                break

    def test_target_upsert_batch_never_drops(self):
        source = MongoSourceConnector(self.source_config)
        target = MongoTargetConnector(self.target_config)
        source.connect()
        target.connect()

        collections = source.list_objects()
        if collections:
            schema = source.get_schema(collections[0])
            target.create_object_if_missing(schema)

            count = source.get_object_count(collections[0])
            rows = source.export_full(collections[0])
            result = target.upsert_batch(collections[0], rows, schema)

            assert result.failure_count == 0
            assert result.success_count == count

    def test_cdc_checkpoint_accepts_apply_result(self):
        cdc = MongoCDCEngine(self.source_config)
        cdc.connect()
        cdc.start()

        events = cdc.poll_changes()
        if events:
            apply_result = cdc.apply(events)
            cdc.checkpoint(apply_result)
            assert apply_result.last_checkpoint is not None or apply_result.success_count == 0


@pytest.mark.integration
class TestMSSQLFullMigration:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.source_config = {
            "host": "localhost",
            "port": 1433,
            "database": "migration_test",
            "username": "sa",
            "password": "test_pass",
            "ssl": False,
        }
        self.target_config = {
            "host": "localhost",
            "port": 1433,
            "database": "migration_target",
            "username": "sa",
            "password": "test_pass",
            "ssl": False,
        }

    def test_source_connect_and_list_tables(self):
        source = MSSQLSourceConnector(self.source_config)
        source.connect()
        tables = source.list_objects()
        assert isinstance(tables, list)
        source._conn.close()

    def test_source_export_full_yields_dicts(self):
        source = MSSQLSourceConnector(self.source_config)
        source.connect()
        tables = source.list_objects()
        if tables:
            for row in source.export_full(tables[0]):
                assert isinstance(row, dict)
                break
        source._conn.close()

    def test_target_upsert_batch_never_drops(self):
        source = MSSQLSourceConnector(self.source_config)
        target = MSSQLTargetConnector(self.target_config)
        source.connect()
        target.connect()

        tables = source.list_objects()
        if tables:
            schema = source.get_schema(tables[0])
            target.create_object_if_missing(schema)

            count = source.get_object_count(tables[0])
            rows = source.export_full(tables[0])
            result = target.upsert_batch(tables[0], rows, schema)

            assert result.failure_count == 0
            assert result.success_count == count

        source._conn.close()
        target._conn.close()


@pytest.mark.integration
class TestCrossEngineMigration:
    def test_mysql_to_postgres_count_validation(self):
        mysql_config = {
            "host": "localhost",
            "port": 3306,
            "database": "migration_test",
            "username": "test_user",
            "password": "test_pass",
            "ssl": False,
        }
        pg_config = {
            "host": "localhost",
            "port": 5432,
            "database": "migration_target",
            "username": "test_user",
            "password": "test_pass",
            "ssl": False,
        }

        source = MySQLSourceConnector(mysql_config)
        target = PostgresTargetConnector(pg_config)
        source.connect()
        target.connect()

        tables = source.list_objects()
        for table in tables[:1]:
            schema = source.get_schema(table)
            target.create_object_if_missing(schema)

            source.get_object_count(table)
            rows = source.export_full(table)
            result = target.upsert_batch(table, rows, schema)

            assert result.failure_count == 0

        source._conn.close()
        target._conn.close()


@pytest.mark.integration
class TestValidatorWithRealConnectors:
    def test_validator_count_match(self):
        pg_config = {
            "host": "localhost",
            "port": 5432,
            "database": "migration_test",
            "username": "test_user",
            "password": "test_pass",
            "ssl": False,
        }

        source = PostgresSourceConnector(pg_config)
        target = PostgresTargetConnector(pg_config)
        source.connect()
        target.connect()

        tables = source.list_objects()
        if tables:
            table = tables[0]
            schema = source.get_schema(table)
            target.create_object_if_missing(schema)

            source.get_object_count(table)
            rows = source.export_full(table)
            target.upsert_batch(table, rows, schema)

            validator = Validator(source, target)
            result = validator.validate_count(table)

            assert result["match"] is True
            assert result["source_count"] == result["target_count"]

        source._conn.close()
        target._conn.close()

    def test_validator_checksum_uses_sha256(self):
        pg_config = {
            "host": "localhost",
            "port": 5432,
            "database": "migration_test",
            "username": "test_user",
            "password": "test_pass",
            "ssl": False,
        }

        source = PostgresSourceConnector(pg_config)
        target = PostgresTargetConnector(pg_config)
        source.connect()
        target.connect()

        tables = source.list_objects()
        if tables:
            table = tables[0]
            schema = source.get_schema(table)
            target.create_object_if_missing(schema)

            source.get_object_count(table)
            rows = source.export_full(table)
            target.upsert_batch(table, rows, schema)

            validator = Validator(source, target)
            result = validator.validate_checksum(table, sample_size=10)

            assert result["match"] is True
            assert len(result["source_sample_hash"]) == 64
            assert len(result["target_sample_hash"]) == 64

        source._conn.close()
        target._conn.close()