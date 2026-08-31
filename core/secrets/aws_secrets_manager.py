from __future__ import annotations

from typing import Any

from core.retry import retry_with_backoff
from core.secrets.base import SecretProvider


class AWSSecretsManagerProvider(SecretProvider):
    def __init__(self, region: str = "us-east-1") -> None:
        self._region = region
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            import boto3

            self._client = boto3.client("secretsmanager", region_name=self._region)
        return self._client

    @retry_with_backoff(max_retries=3, base_delay=1.0)
    def get_secret(self, name: str) -> str:
        client = self._get_client()
        response = client.get_secret_value(SecretId=name)
        secret_string = response.get("SecretString")
        if secret_string is None:
            raise ValueError(f"Secret '{name}' does not contain a string value")
        return secret_string
