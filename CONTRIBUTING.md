# Как вносить изменения

Прямые коммиты в `main` запрещены: все изменения проходят через pull request.

## Порядок работы

```bash
git checkout main
git pull
git checkout -b feature/US-03-otp-verify

# пишем код и тесты
cd services/api
ruff format .
ruff check .
pytest

git add .
git commit -m "feat(auth): add OTP verification (US-03)"
git push -u origin feature/US-03-otp-verify
```

Затем откройте pull request в `main` на GitHub.

## Ветки

Формат: `<тип>/<US-номер>-<кратко>`.

- `feature/US-03-otp-verify`: новая функциональность
- `fix/US-12-history-order`: исправление ошибки
- `chore/update-dependencies`: обслуживание

## Коммиты

Формат: `<тип>(<модуль>): <что сделано> (US-номер)`.

Типы: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`.

## Требования к pull request

- Один pull request решает одну задачу и по возможности остаётся небольшим.
- Проходят все проверки CI.
- Новая логика покрыта тестами.
- Изменение схемы БД сопровождается миграцией.
- Изменение API отражено в схемах, чтобы OpenAPI оставался актуальным.
- Получено минимум одно одобрение.
- Секреты, пароли и OTP-коды не попадают в код и логи.
