from __future__ import annotations

import json
import os
from typing import Any

from core.retry import retry_with_backoff
from core.secrets.base import SecretProvider


class LocalEncryptedFileProvider(SecretProvider):
    def __init__(
        self,
        file_path: str = "secrets.enc",
        key_source: str = "env",
        key_env_var: str = "MIGRATION_SECRETS_KEY",
        keyring_service: str = "migration-platform/secrets-key",
        auto_create: bool = False,
    ) -> None:
        self._file_path = file_path
        self._key_source = key_source
        self._key_env_var = key_env_var
        self._keyring_service = keyring_service
        self._auto_create = auto_create
        self._key = self._load_key()
        self._secrets: dict[str, str] = self._load_secrets()

    def _load_key(self) -> bytes:
        if self._key_source == "keyring":
            try:
                import keyring

                key = keyring.get_password(self._keyring_service, "encryption-key")
            except Exception as exc:
                raise RuntimeError(
                    f"keyring lookup failed for service '{self._keyring_service}': {exc}"
                ) from exc
            if key is None:
                raise RuntimeError(
                    f"Encryption key not found in keyring service '{self._keyring_service}'. "
                    f"Store the key first or switch key_source to 'env'."
                )
        else:
            key = os.environ.get(self._key_env_var)
            if key is None:
                raise RuntimeError(
                    f"Encryption key not found in environment variable {self._key_env_var}."
                )

        key_bytes = key.encode("utf-8")
        return key_bytes

    def _get_fernet(self) -> Any:
        from cryptography.fernet import Fernet

        return Fernet(self._key)

    def _load_secrets(self) -> dict[str, str]:
        if not os.path.exists(self._file_path):
            if self._auto_create:
                self._save_secrets({})
                return {}
            return {}
        try:
            with open(self._file_path, "rb") as f:
                encrypted = f.read()
            if not encrypted:
                return {}
            fernet = self._get_fernet()
            decrypted = fernet.decrypt(encrypted)
            return json.loads(decrypted.decode("utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def _save_secrets(self, secrets: dict[str, str]) -> None:
        fernet = self._get_fernet()
        plaintext = json.dumps(secrets).encode("utf-8")
        encrypted = fernet.encrypt(plaintext)
        with open(self._file_path, "wb") as f:
            f.write(encrypted)

    @retry_with_backoff(max_retries=3, base_delay=0.1)
    def get_secret(self, name: str) -> str:
        if name not in self._secrets:
            raise KeyError(f"Secret '{name}' not found in encrypted file '{self._file_path}'")
        return self._secrets[name]
