#!/usr/bin/env python3
"""Bootstrap script: install dependencies and verify drivers."""

from __future__ import annotations

import platform
import shutil
import subprocess
import sys
from typing import Any

ENGINE_IMPORTS: dict[str, dict[str, Any]] = {
    "postgresql": {"imports": ["psycopg"], "label": "PostgreSQL (psycopg)"},
    "mysql": {"imports": ["mysql.connector", "pymysqlreplication"], "label": "MySQL (mysql-connector-python, mysql-replication)"},
    "mongodb": {"imports": ["pymongo"], "label": "MongoDB (pymongo)"},
    "mssql": {"imports": ["pyodbc"], "odbc_check": "ODBC Driver 18 for SQL Server", "label": "MSSQL (pyodbc + ODBC Driver 18)"},
    "cosmos_mongo": {"imports": ["pymongo", "azure.cosmos"], "label": "Cosmos DB (pymongo, azure-cosmos)"},
}


def run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, **kwargs)


def install_pip_requirements() -> None:
    req_file = "requirements.txt"
    if not shutil.which("pip"):
        print("pip not found. Install Python first.")
        sys.exit(1)
    print(f"Installing Python dependencies from {req_file}...")
    result = run([sys.executable, "-m", "pip", "install", "-r", req_file])
    if result.returncode != 0:
        print(result.stderr)
        sys.exit(1)
    print("Python dependencies installed.")


def detect_configured_engines(config_path: str | None = None) -> list[str]:
    if config_path is None:
        return list(ENGINE_IMPORTS.keys())
    import yaml

    with open(config_path) as f:
        config = yaml.safe_load(f) or {}
    source = config.get("source", {}).get("engine")
    target = config.get("target", {}).get("engine")
    engines = {source, target}
    return [e for e in engines if e in ENGINE_IMPORTS]


def check_imports(engines: list[str]) -> bool:
    ok = True
    for engine in engines:
        spec = ENGINE_IMPORTS.get(engine)
        if spec is None:
            continue
        for mod in spec.get("imports", []):
            try:
                __import__(mod)
            except ImportError:
                print(f"MISSING: {mod} ({spec['label']})")
                ok = False
            else:
                print(f"OK: {mod}")
        if "odbc_check" in spec:
            try:
                import pyodbc

                drivers = pyodbc.drivers()
                if spec["odbc_check"] not in drivers:
                    print(f"MISSING ODBC DRIVER: {spec['odbc_check']} not found in pyodbc.drivers()")
                    ok = False
                else:
                    print(f"OK: {spec['odbc_check']}")
            except ImportError:
                print(f"MISSING: pyodbc ({spec['label']})")
                ok = False
    return ok


def print_odbc_install_instructions() -> None:
    system = platform.system()
    print("\nMSSQL ODBC driver missing. Install it manually:")
    if system == "Windows":
        print("  choco install msodbcsql18")
    elif system == "Darwin":
        print("  brew tap microsoft/mssql-release && brew install msodbcsql18")
    elif system == "Linux":
        print("  curl https://packages.microsoft.com/keys/microsoft.asc | sudo apt-key add -")
        print("  curl https://packages.microsoft.com/config/$(lsb_release -rs)/prod.list | sudo tee /etc/apt/sources.list.d/mssql-release.list")
        print("  sudo apt-get update && sudo ACCEPT_EULA=Y apt-get install -y msodbcsql18")
    else:
        print(f"  Unknown OS ({system}). Install ODBC Driver 18 for SQL Server manually.")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Bootstrap migration platform dependencies")
    parser.add_argument("--config", help="Path to YAML config file")
    parser.add_argument("--skip-pip", action="store_true", help="Skip pip install")
    args = parser.parse_args()

    if not args.skip_pip:
        install_pip_requirements()

    engines = detect_configured_engines(args.config)
    print(f"\nVerifying drivers for engines: {', '.join(engines)}")
    all_ok = check_imports(engines)
    if not all_ok and "mssql" in engines:
        print_odbc_install_instructions()
        sys.exit(1)
    if not all_ok:
        sys.exit(1)
    print("\nAll dependencies satisfied.")


if __name__ == "__main__":
    main()
