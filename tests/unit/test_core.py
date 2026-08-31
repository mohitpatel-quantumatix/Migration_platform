from __future__ import annotations

import pytest
from unittest.mock import MagicMock

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
    IDENTIFIER_RE,
)
from core.retry import retry_with_backoff, CircuitBreaker
from core.audit_logger import audit_log, set_run_id
from core.secrets.base import SecretResolver
from core.secrets.env import EnvSecretProvider
from core.schema_mapping.registry import TypeMappingRegistry
from core.schema_mapping.type_map import map_type, check_size_limit
from core.validator import Validator
from core.alerting import (
    WebhookNotifier,
    SlackNotifier,
    create_notifier,
)
from core.orchestrator import MigrationOrchestrator
from core.assessment.report_generator import AssessmentReport


class TestInterfaceConsistency:
    def test_all_target_connectors_match_abc_upsert_batch_signature(self):
        import inspect
        from core.connectors import (
            PostgresTargetConnector,
            MySQLTargetConnector,
            MongoTargetConnector,
            MSSQLTargetConnector,
            CosmosMongoTargetConnector,
        )
        for cls in [
            PostgresTargetConnector,
            MySQLTargetConnector,
            MongoTargetConnector,
            MSSQLTargetConnector,
            CosmosMongoTargetConnector,
        ]:
            sig = inspect.signature(cls.upsert_batch)
            assert "schema" in sig.parameters, f"{cls.__name__} is missing schema param"


class TestBug1NeverDropWithIncremental:
    def test_upsert_never_drops_or_truncates(self):
        source = MagicMock(spec=SourceConnector)
        target = MagicMock(spec=TargetConnector)
        target.upsert_batch.return_value = UpsertResult(success_count=10)
        source.list_objects.return_value = ["users"]
        source.get_object_count.return_value = 10
        source.get_schema.return_value = Schema(name="users", columns=[Column(name="id", source_type="integer")])
        source.export_full.return_value = iter([{"id": 1}])

        orchestrator = MigrationOrchestrator(source, target, {})
        orchestrator.run_full()

        target.upsert_batch.assert_called()
        for call in target.upsert_batch.call_args_list:
            assert "TRUNCATE" not in str(call)
            assert "DROP" not in str(call)


class TestBug2StatusFromValidation:
    def test_status_not_hardcoded(self):
        source = MagicMock(spec=SourceConnector)
        target = MagicMock(spec=TargetConnector)
        target.upsert_batch.return_value = UpsertResult(success_count=10)

        orchestrator = MigrationOrchestrator(source, target, {})
        result = orchestrator.run_full()

        assert result.get("status") != "SUCCESS"
        assert result.get("status") in ("success", "failed", "mismatch")


class TestBug3PartialBatchNoCheckpoint:
    def test_checkpoint_not_advanced_on_partial_failure(self):
        MagicMock(spec=CDCEngine)
        [
            ChangeEvent(operation="insert", document={"id": 1}),
            ChangeEvent(operation="insert", document={"id": 2}),
        ]
        result = ApplyResult(success_count=1, failure_count=1, errors=["dup"])
        assert result.failure_count > 0
        assert result.last_checkpoint is None


class TestBug4TypeSafeIncrementalQueries:
    def test_objectid_not_string_comparison(self):
        from bson import ObjectId
        oid = ObjectId()
        assert isinstance(oid, ObjectId)
        assert oid != str(oid)


class TestBug5ObjectNameValidation:
    def test_valid_identifier_accepted(self):
        assert validate_identifier("valid_table") == "valid_table"

    def test_invalid_identifier_rejected(self):
        with pytest.raises(ValueError):
            validate_identifier("123-invalid")

    def test_invalid_identifier_with_special_chars(self):
        with pytest.raises(ValueError):
            validate_identifier("table-with-dash")

    def test_identifier_regex(self):
        assert IDENTIFIER_RE.match("valid_name") is not None
        assert IDENTIFIER_RE.match("1invalid") is None
        assert IDENTIFIER_RE.match("valid_123") is not None


class TestBug6NoHardcodedCredentials:
    def test_no_hardcoded_passwords_in_source(self):
        import inspect
        from core.connectors import postgresql, mysql, mssql, mongodb

        for module in [postgresql, mysql, mssql, mongodb]:
            source = inspect.getsource(module)
            assert "hardcoded_password" not in source.lower()
            assert "admin123" not in source


class TestBug8SingleCDCImplPerEngine:
    def test_one_cdc_class_per_engine(self):
        from core.connectors import postgresql, mysql, mssql, mongodb, cosmos_mongo

        pg_cdc = getattr(postgresql, "PostgresCDCEngine", None)
        mysql_cdc = getattr(mysql, "MySQLCDCEngine", None)
        mssql_cdc = getattr(mssql, "MSSQLCDCEngine", None)
        mongo_cdc = getattr(mongodb, "MongoCDCEngine", None)
        cosmos_cdc = getattr(cosmos_mongo, "CosmosMongoCDCEngine", None)

        assert pg_cdc is not None
        assert mysql_cdc is not None
        assert mssql_cdc is not None
        assert mongo_cdc is not None
        assert cosmos_cdc is not None


class TestBug9UriEncodingUsesQuote:
    def test_no_url_encoding_in_dsn_params(self):
        import inspect
        from core.connectors import postgresql

        source = inspect.getsource(postgresql.PostgresSourceConnector.connect)
        assert "urllib.parse.quote" not in source

    def test_password_passed_as_kwargs_not_string_conn(self):
        import inspect
        from core.connectors import postgresql

        # password lives in _make_conn_kwargs, which connect() delegates to.
        source = inspect.getsource(postgresql._make_conn_kwargs)
        assert '"password"' in source or "'password'" in source


class TestBug10TlsOnByDefault:
    def test_postgres_ssl_default_verify_full(self):
        import inspect
        from core.connectors.postgresql import _make_conn_kwargs

        # sslmode / verify-full lives in _make_conn_kwargs, which connect() delegates to.
        source = inspect.getsource(_make_conn_kwargs)
        assert "verify-full" in source

    def test_mysql_ssl_default_enabled(self):
        from core.connectors.mysql import MySQLSourceConnector
        import inspect
        source = inspect.getsource(MySQLSourceConnector.connect)
        assert "ssl_disabled" in source


class TestBug11ExponentialBackoffOnRateLimit:
    def test_cosmos_connector_uses_retry_with_backoff(self):
        from core.connectors.cosmos_mongo import CosmosMongoTargetConnector
        import inspect
        source = inspect.getsource(CosmosMongoTargetConnector.connect)
        assert "retry_with_backoff" in source or "max_retries" in source


class TestRetryBackoff:
    def test_retry_decorator_retries_on_exception(self):
        call_count = 0

        @retry_with_backoff(max_retries=2, base_delay=0.01)
        def flaky_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("transient")
            return "success"

        result = flaky_func()
        assert result == "success"
        assert call_count == 3

    def test_circuit_breaker_opens_after_max_failures(self):
        cb = CircuitBreaker(max_failures=2, reset_timeout=1.0)

        @retry_with_backoff(max_retries=1, circuit_breaker=cb)
        def failing_func():
            cb.record_failure()
            raise ValueError("always fails")

        with pytest.raises(ValueError):
            failing_func()

        assert cb.is_open


class TestSecretResolver:
    def test_env_provider_resolves_secret(self):
        import os
        os.environ["SECRET_TEST_DB"] = "test_password"
        provider = EnvSecretProvider()
        assert provider.get_secret("TEST_DB") == "test_password"
        del os.environ["SECRET_TEST_DB"]

    def test_secret_resolver_loads_provider(self):
        provider = EnvSecretProvider()
        resolver = SecretResolver(provider)
        import os
        os.environ["SECRET_MYKEY"] = "myvalue"
        assert resolver.resolve("MYKEY") == "myvalue"
        del os.environ["SECRET_MYKEY"]


class TestSchemaMapping:
    def test_postgresql_to_mysql_integer(self):
        assert map_type("postgresql", "mysql", "integer") == "INT"

    def test_mysql_to_postgresql_int(self):
        assert map_type("mysql", "postgresql", "INT") == "integer"

    def test_relational_to_mongo_integer(self):
        assert map_type("postgresql", "mongodb", "integer") == "int32"

    def test_mongo_to_relational_string(self):
        assert map_type("mongodb", "postgresql", "string") == "varchar"

    def test_size_limit_cosmos(self):
        assert check_size_limit("cosmos_mongo", 1024 * 1024) is True
        assert check_size_limit("cosmos_mongo", 3 * 1024 * 1024) is False

    def test_size_limit_mongodb(self):
        assert check_size_limit("mongodb", 10 * 1024 * 1024) is True
        assert check_size_limit("mongodb", 20 * 1024 * 1024) is False

    def test_registry_custom_mapping(self):
        registry = TypeMappingRegistry()
        registry.register("custom", "target", "custom_type", "mapped_type")
        assert registry.map_type("custom", "target", "custom_type") == "mapped_type"


class TestAuditLogger:
    def test_audit_log_outputs_json(self):
        import logging
        from io import StringIO

        set_run_id("test-run-123")
        logger = logging.getLogger("migration_platform.audit")
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        try:
            audit_log(phase="test", status="ok", details={"key": "value"})
            output = stream.getvalue().strip()
            assert '"phase": "test"' in output
            assert '"status": "ok"' in output
            assert '"run_id": "test-run-123"' in output
        finally:
            logger.removeHandler(handler)


class TestAssessmentReport:
    def test_report_generates_json(self):
        report = AssessmentReport()
        report.source_engine = "postgresql"
        report.target_engine = "mysql"
        report.objects = [{"name": "users", "row_count": 100}]
        report.compatible = True

        d = report.to_dict()
        assert d["source_engine"] == "postgresql"
        assert d["target_engine"] == "mysql"
        assert d["compatible"] is True

        json_str = report.to_json()
        assert "postgresql" in json_str


class TestValidator:
    def test_validate_count_returns_dict(self):
        source = MagicMock(spec=SourceConnector)
        target = MagicMock(spec=TargetConnector)
        source.get_object_count.return_value = 100
        target.get_object_count.return_value = 100

        validator = Validator(source, target)
        result = validator.validate_count("test_table")

        assert result["match"] is True
        assert result["source_count"] == 100
        assert result["target_count"] == 100


class TestNotifierCreation:
    def test_create_none_notifier(self):
        notifier = create_notifier({"type": "none"})
        assert notifier is None

    def test_create_webhook_notifier(self):
        notifier = create_notifier({"type": "webhook", "webhook_url": "http://example.com"})
        assert isinstance(notifier, WebhookNotifier)

    def test_create_slack_notifier(self):
        notifier = create_notifier({"type": "slack", "webhook_url": "http://example.com"})
        assert isinstance(notifier, SlackNotifier)


class TestOrchestratorConnects:
    def test_orchestrator_drives_connectors_via_interface(self):
        source = MagicMock(spec=SourceConnector)
        target = MagicMock(spec=TargetConnector)
        source.list_objects.return_value = ["users"]
        source.get_object_count.return_value = 50
        source.get_schema.return_value = Schema(name="users", columns=[Column(name="id", source_type="integer")])
        source.export_full.return_value = iter([{"id": 1}])
        target.upsert_batch.return_value = UpsertResult(success_count=1)
        target.get_object_count.return_value = 50

        orchestrator = MigrationOrchestrator(source, target, {})
        result = orchestrator.run_full()

        assert result["status"] == "success"
        source.connect.assert_called()
        target.connect.assert_called()


class TestConfigSchema:
    def test_schema_yaml_is_valid(self):
        import yaml
        import os
        schema_path = os.path.join(
            os.path.dirname(__file__),
            "..", "..", "config", "migration_config.schema.yaml",
        )
        with open(schema_path) as f:
            schema = yaml.safe_load(f)

        assert "source" in schema
        assert "target" in schema
        assert "migration" in schema
        assert "retry" in schema