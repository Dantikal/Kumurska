import pytest

from app.core.config import Settings
from app.integrations.sms import FakeSmsProvider, build_sms_provider


@pytest.mark.parametrize("env", ["dev", "test"])
def test_fake_provider_allowed_in_dev_and_test(env: str) -> None:
    provider = build_sms_provider(Settings(app_env=env, sms_provider="fake"))
    assert isinstance(provider, FakeSmsProvider)


@pytest.mark.parametrize("env", ["prod", "staging"])
def test_fake_provider_refused_outside_dev_and_test(env: str) -> None:
    with pytest.raises(RuntimeError, match="SMS-провайдер не настроен"):
        build_sms_provider(Settings(app_env=env, sms_provider="fake"))


def test_unknown_provider_refused() -> None:
    with pytest.raises(RuntimeError, match="Неизвестный SMS-провайдер"):
        build_sms_provider(Settings(app_env="dev", sms_provider="nope"))
