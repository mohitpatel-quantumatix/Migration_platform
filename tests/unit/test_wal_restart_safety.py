from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.connectors.base import TargetConnector
from core.orchestrator import MigrationOrchestrator


def _orchestrator(wal_level: str, allow_restart: bool | None = None):
    source = MagicMock()
    target = MagicMock(spec=TargetConnector)
    cursor = MagicMock()
    cursor.fetchone.return_value = (wal_level,)
    source._conn.cursor.return_value.__enter__.return_value = cursor

    config = {}
    if allow_restart is not None:
        config["cdc"] = {"allow_source_service_restart": allow_restart}

    return MigrationOrchestrator(source, target, config), source, cursor


def test_missing_restart_flag_defaults_to_false_and_does_not_restart():
    orchestrator, _, cursor = _orchestrator("replica")

    with patch.object(orchestrator, "_restart_postgresql") as restart:
        with pytest.raises(RuntimeError) as error:
            orchestrator._ensure_wal_level_logical()

    assert orchestrator._allow_source_service_restart is False
    assert restart.call_count == 0
    assert cursor.execute.call_args_list == [(("SHOW wal_level",), {})]
    message = str(error.value)
    assert "wal_level = logical" in message
    assert "Automatic source-service restart is disabled" in message
    assert "cdc.allow_source_service_restart=true" in message


def test_explicit_restart_opt_in_uses_existing_restart_path():
    orchestrator, source, cursor = _orchestrator("replica", allow_restart=True)
    cursor.fetchone.side_effect = [
        ("replica",),
        ("C:/postgres/data/postgresql.conf",),
        ("logical",),
    ]

    with (
        patch.object(Path, "read_text", return_value="wal_level = replica\n"),
        patch.object(Path, "write_text") as write_text,
        patch.object(orchestrator, "_restart_postgresql") as restart,
        patch("core.orchestrator.time.sleep"),
    ):
        orchestrator._ensure_wal_level_logical()

    assert orchestrator._allow_source_service_restart is True
    restart.assert_called_once_with(Path("C:/postgres/data"))
    write_text.assert_called_once()
    source.connect.assert_called_once()


def test_logical_wal_level_remains_a_no_op_without_restart():
    orchestrator, source, _ = _orchestrator("logical")

    with patch.object(orchestrator, "_restart_postgresql") as restart:
        orchestrator._ensure_wal_level_logical()

    restart.assert_not_called()
    source.connect.assert_not_called()
