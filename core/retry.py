from __future__ import annotations

import functools
import random
import time
from collections.abc import Callable
from typing import Any, TypeVar

from core.audit_logger import audit_log

F = TypeVar("F", bound=Callable[..., Any])


class CircuitBreakerError(Exception):
    pass


class CircuitBreaker:
    def __init__(self, max_failures: int = 5, reset_timeout: float = 60.0) -> None:
        self.max_failures = max_failures
        self.reset_timeout = reset_timeout
        self._failure_count = 0
        self._last_failure_time: float | None = None
        self._state = "closed"

    @property
    def is_open(self) -> bool:
        if self._state == "open":
            if self._last_failure_time is not None:
                if time.monotonic() - self._last_failure_time >= self.reset_timeout:
                    self._state = "half_open"
                    return False
            return True
        return False

    def record_success(self) -> None:
        self._failure_count = 0
        self._state = "closed"

    def record_failure(self) -> None:
        self._failure_count += 1
        self._last_failure_time = time.monotonic()
        if self._failure_count >= self.max_failures:
            self._state = "open"


def retry_with_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    jitter: bool = True,
    retry_on: tuple[type[Exception], ...] = (Exception,),
    circuit_breaker: CircuitBreaker | None = None,
) -> Callable[[F], F]:
    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if circuit_breaker is not None and circuit_breaker.is_open:
                raise CircuitBreakerError(
                    f"Circuit breaker open for {func.__module__}.{func.__name__}"
                )

            last_exception: Exception | None = None
            delay = base_delay

            for attempt in range(max_retries + 1):
                try:
                    result = func(*args, **kwargs)
                    if circuit_breaker is not None:
                        circuit_breaker.record_success()
                    return result
                except retry_on as exc:
                    last_exception = exc
                    if circuit_breaker is not None:
                        circuit_breaker.record_failure()

                    if attempt >= max_retries:
                        break

                    sleep_time = delay + (random.uniform(0, delay) if jitter else 0)
                    sleep_time = min(sleep_time, max_delay)
                    audit_log(
                        phase="retry",
                        status="retrying",
                        details={
                            "function": f"{func.__module__}.{func.__name__}",
                            "attempt": attempt + 1,
                            "max_retries": max_retries,
                            "delay_seconds": round(sleep_time, 2),
                            "error": str(exc),
                        },
                    )
                    time.sleep(sleep_time)
                    delay *= 2

            raise last_exception

        return wrapper  # type: ignore[return-value]

    return decorator