from __future__ import annotations

import os
from core.secrets.base import SecretProvider


class EnvSecretProvider(SecretProvider):
    def get_secret(self, name: str) -> str:
        env_name = f"SECRET_{name}"
        value = os.environ.get(env_name)
        if value is None:
            raise KeyError(f"Secret '{name}' not found in environment (looked up as {env_name})")
        return value