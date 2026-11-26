"""Перегенерирует docs/openapi/openapi.json из кода.

Запуск из services/api: uv run python scripts/export_openapi.py
"""

import json
from pathlib import Path

from app.main import app

OUTPUT = Path(__file__).resolve().parents[3] / "docs" / "openapi" / "openapi.json"


def main() -> None:
    OUTPUT.write_text(json.dumps(app.openapi(), indent=2, ensure_ascii=False) + "\n")
    print(f"OpenAPI записан в {OUTPUT}")


if __name__ == "__main__":
    main()
