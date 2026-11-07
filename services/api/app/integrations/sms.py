from typing import Protocol

from app.core.config import Settings, settings

FAKE_SMS_ALLOWED_ENVS = frozenset({"dev", "test"})


class SmsProvider(Protocol):
    async def send(self, phone: str, text: str) -> None: ...


class FakeSmsProvider:
    """Для разработки и тестов: хранит сообщения в памяти и никуда их не отправляет."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    async def send(self, phone: str, text: str) -> None:
        self.sent.append((phone, text))


def build_sms_provider(config: Settings) -> SmsProvider:
    """Выбирает провайдера по SMS_PROVIDER. Неподходящая конфигурация прерывает запуск.

    FakeSmsProvider разрешён только при APP_ENV=dev или test: в остальных окружениях
    коды никуда бы не уходили, и пользователи не смогли бы зарегистрироваться.
    """
    name = config.sms_provider.strip().lower()
    if name == "fake":
        if config.app_env not in FAKE_SMS_ALLOWED_ENVS:
            raise RuntimeError(
                f"SMS-провайдер не настроен: SMS_PROVIDER=fake недопустим при "
                f"APP_ENV={config.app_env}, разрешён только в dev и test"
            )
        return FakeSmsProvider()
    raise RuntimeError(f"Неизвестный SMS-провайдер: SMS_PROVIDER={config.sms_provider}")


_provider: SmsProvider = build_sms_provider(settings)


def get_sms_provider() -> SmsProvider:
    """FastAPI-зависимость. В тестах подменяется через app.dependency_overrides."""
    return _provider
