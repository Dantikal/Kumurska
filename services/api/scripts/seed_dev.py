from datetime import UTC, datetime

from app.core.config import settings

if settings.app_env != "dev":
    raise SystemExit("Seed script разрешён только в dev-окружении.")

from sqlalchemy import select

from app.core.database import SessionLocal, engine
from app.modules.content.models import (
    LegalDocument,
    LegalDocumentStatus,
    LegalDocumentType,
)


async def seed_documents() -> None:
    documents = [
        {
            "type": LegalDocumentType.TERMS,
            "version": 1,
            "title": "Условия бонусной программы (Черновик)",
            "content": (
                "Черновик. Временный текст для разработки. "
                "Не является действующим юридическим документом."
            ),
        },
        {
            "type": LegalDocumentType.PRIVACY,
            "version": 1,
            "title": "Политика конфиденциальности (Черновик)",
            "content": (
                "Черновик. Временный текст для разработки. "
                "Не является действующим юридическим документом."
            ),
        },
    ]

    async with SessionLocal() as session:
        async with session.begin():
            for data in documents:
                query = select(LegalDocument).where(
                    LegalDocument.type == data["type"],
                    LegalDocument.version == data["version"],
                )
                existing = await session.scalar(query)

                if existing is not None:
                    print(f"Документ {data['type'].value} уже существует. Пропускаем.")
                    continue

                document = LegalDocument(
                    **data,
                    status=LegalDocumentStatus.PUBLISHED,
                    published_at=datetime.now(UTC),
                )
                session.add(document)

                print(f"Добавлен документ: {data['type'].value}")


async def main() -> None:
    try:
        await seed_documents()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
