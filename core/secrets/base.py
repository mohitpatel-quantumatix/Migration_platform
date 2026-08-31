from __future__ import annotations

import abc


class SecretProvider(abc.ABC):
    @abc.abstractmethod
    def get_secret(self, name: str) -> str:
        ...


class SecretResolver:
    def __init__(self, provider: SecretProvider) -> None:
        self._provider = provider

    def resolve(self, secret_ref: str) -> str:
        if not secret_ref:
            return ""
        return self._provider.get_secret(secret_ref)

    def resolve_all(self, mapping: dict[str, str]) -> dict[str, str]:
        return {key: self.resolve(value) for key, value in mapping.items()}