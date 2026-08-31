"""
driver_installer.py — Auto-install database drivers on first use.

When a connector's connect() method runs and the required driver
is not installed, this module installs it automatically via pip,
then re-imports it so the caller gets a working module reference.

Usage inside any connector:
    from core.driver_installer import ensure_driver
    ensure_driver("mysql-connector-python", import_name="mysql.connector")
"""
from __future__ import annotations

import importlib
import subprocess
import sys
from core.audit_logger import audit_log


# Maps pip package name → importable module name (when they differ)
_DRIVER_MAP: dict[str, str] = {
    "psycopg":                  "psycopg",
    "mysql-connector-python":   "mysql.connector",
    "pyodbc":                   "pyodbc",
    "pymongo":                  "pymongo",
}


def ensure_driver(pip_package: str, import_name: str | None = None) -> None:
    """
    Ensure *pip_package* is installed and importable.

    If the package is not present, it is installed automatically via pip
    and an audit log entry is written.  Raises RuntimeError if installation
    fails (e.g. no internet access).

    Args:
        pip_package:  The pip install name  (e.g. "mysql-connector-python")
        import_name:  The Python import name if different (e.g. "mysql.connector").
                      Defaults to pip_package if not given.
    """
    module_name = import_name or _DRIVER_MAP.get(pip_package, pip_package)

    # Fast path — already installed
    try:
        importlib.import_module(module_name)
        return
    except ImportError:
        pass

    # Not installed — install it now
    audit_log(
        phase="driver_install",
        status="installing",
        details={"package": pip_package, "module": module_name},
    )
    print(
        f"\n[migration-platform] Driver '{pip_package}' not found. "
        f"Installing automatically...",
        flush=True,
    )

    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", pip_package, "--quiet"],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        audit_log(
            phase="driver_install",
            status="failed",
            details={"package": pip_package, "error": result.stderr.strip()},
        )
        raise RuntimeError(
            f"Failed to auto-install '{pip_package}'.\n"
            f"Please run manually:  pip install {pip_package}\n"
            f"Error: {result.stderr.strip()}"
        )

    audit_log(
        phase="driver_install",
        status="installed",
        details={"package": pip_package},
    )
    print(
        f"[migration-platform] '{pip_package}' installed successfully.\n",
        flush=True,
    )

    # Verify the install worked
    try:
        importlib.import_module(module_name)
    except ImportError as exc:
        raise RuntimeError(
            f"Installed '{pip_package}' but still cannot import '{module_name}'.\n"
            f"Error: {exc}"
        ) from exc
