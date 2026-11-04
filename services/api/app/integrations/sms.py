from typing import Protocol


class SmsProvider(Protocol):
    async def send(self, phone: str, text: str) -> None: ...


class FakeSmsProvider:
    """Для разработки и тестов: хранит сообщения в памяти и никуда их не отправляет."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    async def send(self, phone: str, text: str) -> None:
        self.sent.append((phone, text))
