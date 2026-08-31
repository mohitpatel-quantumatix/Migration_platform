from __future__ import annotations

from typing import Any

from core.retry import retry_with_backoff
from core.secrets.base import SecretProvider


class GCPSecretManagerProvider(SecretProvider):
    def __init__(self, project_id: str) -> None:
        self._project_id = project_id
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            from google.cloud import secretmanager

            self._client = secretmanager.SecretManagerServiceClient()
        return self._client

    @retry_with_backoff(max_retries=3, base_delay=1.0)
    def get_secret(self, name: str) -> str:
        client = self._get_client()
        project_path = f"projects/{self._project_id}/secrets/{name}/versions/latest"
        response = client.access_secret_version(name=project_path)
        payload = response.payload.data.decode("utf-8")
        return payload
