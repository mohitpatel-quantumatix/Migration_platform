from __future__ import annotations

import abc
from typing import Any


class Notifier(abc.ABC):
    @abc.abstractmethod
    def notify(self, event: dict[str, Any]) -> None:
        ...


class WebhookNotifier(Notifier):
    def __init__(self, webhook_url: str) -> None:
        self._webhook_url = webhook_url

    def notify(self, event: dict[str, Any]) -> None:
        import requests
        try:
            requests.post(self._webhook_url, json=event, timeout=10)
        except Exception:
            pass


class SlackNotifier(Notifier):
    def __init__(self, webhook_url: str) -> None:
        self._webhook_url = webhook_url

    def notify(self, event: dict[str, Any]) -> None:
        import requests
        payload = {"text": self._format_message(event)}
        try:
            requests.post(self._webhook_url, json=payload, timeout=10)
        except Exception:
            pass

    def _format_message(self, event: dict[str, Any]) -> str:
        phase = event.get("phase", "unknown")
        status = event.get("status", "unknown")
        details = event.get("details", {})
        return f"[{phase}] {status}: {details}"


class TeamsNotifier(Notifier):
    def __init__(self, webhook_url: str) -> None:
        self._webhook_url = webhook_url

    def notify(self, event: dict[str, Any]) -> None:
        import requests
        payload = {"text": self._format_message(event)}
        try:
            requests.post(self._webhook_url, json=payload, timeout=10)
        except Exception:
            pass

    def _format_message(self, event: dict[str, Any]) -> str:
        phase = event.get("phase", "unknown")
        status = event.get("status", "unknown")
        details = event.get("details", {})
        return f"[{phase}] {status}: {details}"


class EmailNotifier(Notifier):
    def __init__(self, smtp_server: str, smtp_port: int, sender: str, recipients: list[str]) -> None:
        self._smtp_server = smtp_server
        self._smtp_port = smtp_port
        self._sender = sender
        self._recipients = recipients

    def notify(self, event: dict[str, Any]) -> None:
        import smtplib
        from email.mime.text import MIMEText

        subject = f"Migration Alert: {event.get('phase', 'unknown')} - {event.get('status', 'unknown')}"
        body = str(event)
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = self._sender
        msg["To"] = ", ".join(self._recipients)

        try:
            with smtplib.SMTP(self._smtp_server, self._smtp_port) as server:
                server.sendmail(self._sender, self._recipients, msg.as_string())
        except Exception:
            pass


def create_notifier(config: dict[str, Any]) -> Notifier | None:
    notifier_type = config.get("type", "none")
    if notifier_type == "none":
        return None
    elif notifier_type == "webhook":
        return WebhookNotifier(config["webhook_url"])
    elif notifier_type == "slack":
        return SlackNotifier(config["webhook_url"])
    elif notifier_type == "teams":
        return TeamsNotifier(config["webhook_url"])
    elif notifier_type == "email":
        return EmailNotifier(
            config["smtp_server"],
            config["smtp_port"],
            config["sender"],
            config["recipients"],
        )
    return None