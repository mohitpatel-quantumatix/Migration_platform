from __future__ import annotations

from typing import Any

from core.retry import retry_with_backoff
from core.secrets.base import SecretProvider


class HashiCorpVaultProvider(SecretProvider):
    def __init__(
        self,
        url: str,
        token: str,
        mount_point: str = "secret",
    ) -> None:
        self._url = url
        self._token = token
        self._mount_point = mount_point
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            import hvac

            self._client = hvac.Client(url=self._url, token=self._token)
        return self._client

    @retry_with_backoff(max_retries=3, base_delay=1.0)
    def get_secret(self, name: str) -> str:
        client = self._get_client()
        response = client.secrets.kv.read_secret_version(
            path=name,
            mount_point=self._mount_point,
        )
        data = response["data"]["data"]
        value = data.get("value")
        if value is None:
            raise KeyError(f"Secret '{name}' not found at mount point '{self._mount_point}'")
        return str(value)
