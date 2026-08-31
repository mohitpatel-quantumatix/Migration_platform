"""
Report uploader — publishes the self-contained HTML report to Azure Blob Storage
and returns a publicly-accessible (SAS) URL that can be shared with anyone.

Config (in config.yaml under reporting.azure_blob):
  reporting:
    azure_blob:
      connection_string: "DefaultEndpointsProtocol=https;AccountName=..."
      container_name: "migration-reports"        # created automatically if absent
      sas_expiry_days: 90                         # optional, default 90

The package azure-storage-blob is auto-installed on first use.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from core.driver_installer import ensure_driver


def upload_report(
    html_path: str,
    json_path: str,
    run_id: str,
    azure_cfg: dict[str, Any],
) -> dict[str, str]:
    """
    Upload HTML + JSON reports to Azure Blob Storage.

    Returns a dict with:
        html_url  - shareable SAS URL for the HTML report
        json_url  - shareable SAS URL for the JSON report
        container - blob container name
        expiry    - SAS expiry ISO timestamp
    """
    ensure_driver("azure-storage-blob", "azure.storage.blob")

    from azure.storage.blob import (  # type: ignore[import]
        BlobServiceClient,
        BlobSasPermissions,
        generate_blob_sas,
    )

    conn_str     = azure_cfg.get("connection_string", "")
    container    = azure_cfg.get("container_name", "migration-reports")
    expiry_days  = int(azure_cfg.get("sas_expiry_days", 90))

    if not conn_str:
        raise ValueError(
            "reporting.azure_blob.connection_string is required for Azure upload. "
            "Set it in your config.yaml."
        )

    client = BlobServiceClient.from_connection_string(conn_str)

    # Create container if it doesn't exist (public blob access off by default)
    try:
        client.create_container(container)
    except Exception:
        pass  # already exists

    expiry = datetime.now(UTC) + timedelta(days=expiry_days)

    def _upload_and_sas(local_path: str, blob_name: str, content_type: str) -> str:
        blob_client = client.get_blob_client(container=container, blob=blob_name)
        with open(local_path, "rb") as f:
            blob_client.upload_blob(
                f,
                overwrite=True,
                content_settings=type("CS", (), {"content_type": content_type})(),
            )
        # Parse account name + key from connection string for SAS generation
        parts = dict(p.split("=", 1) for p in conn_str.split(";") if "=" in p)
        account_name = parts.get("AccountName", "")
        account_key  = parts.get("AccountKey", "")

        sas = generate_blob_sas(
            account_name=account_name,
            container_name=container,
            blob_name=blob_name,
            account_key=account_key,
            permission=BlobSasPermissions(read=True),
            expiry=expiry,
        )
        return f"https://{account_name}.blob.core.windows.net/{container}/{blob_name}?{sas}"

    html_url = _upload_and_sas(
        html_path,
        f"{run_id}/{run_id}.html",
        "text/html; charset=utf-8",
    )
    json_url = _upload_and_sas(
        json_path,
        f"{run_id}/{run_id}.json",
        "application/json",
    )

    return {
        "html_url":  html_url,
        "json_url":  json_url,
        "container": container,
        "expiry":    expiry.isoformat(),
    }
