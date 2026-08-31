from __future__ import annotations

import logging
from typing import Any

from core.secrets.base import SecretProvider

logger = logging.getLogger("migration_platform.secrets")


class AzureKeyVaultProvider(SecretProvider):
    def __init__(self, vault_url: str, credential: Any = None) -> None:
        self._vault_url = vault_url
        self._credential = credential
        self._client: Any = None

    def _get_client(self):
        if self._client is not None:
            return self._client
        try:
            from azure.keyvault.secrets import SecretClient
            from azure.identity import DefaultAzureCredential
        except ImportError:
            logger.warning(
                "azure-keyvault-secrets or azure-identity not installed; "
                "Azure Key Vault secret resolution unavailable"
            )
            return None

        credential = self._credential or DefaultAzureCredential()
        self._client = SecretClient(vault_url=self._vault_url, credential=credential)
        return self._client

    def get_secret(self, name: str) -> str:
        client = self._get_client()
        if client is None:
            raise RuntimeError(
                f"Cannot resolve secret '{name}': Azure Key Vault SDK not available"
            )
        retrieved = client.get_secret(name)
        return retrieved.value