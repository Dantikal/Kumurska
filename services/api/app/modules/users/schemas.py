# app/modules/users/schemas.py
from datetime import date
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


class UserRead(BaseModel):
    id: UUID
    phone: str
    name: str
    birth_date: date
    status: str

    model_config = {"from_attributes": True}


class UserUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    birth_date: date | None = None

    @field_validator("name", mode="before")
    @classmethod
    def clean_name(cls, value):
        if value is None:
            raise ValueError("Имя не может быть пустым")
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("birth_date")
    @classmethod
    def validate_birth_date(cls, value):
        if value is None:
            raise ValueError("Дата рождения не может быть пустой")
        if value > date.today():
            raise ValueError("Дата рождения не может быть в будущем")
        return value

    @model_validator(mode="after")
    def check_at_least_one_field(self):
        if not self.model_fields_set:
            raise ValueError("Необходимо указать хотя бы одно поле для обновления")
        return self

    def get_updated_fields(self):
        return self.model_dump(exclude_unset=True)
