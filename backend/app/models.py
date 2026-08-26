from typing import Any

from pydantic import BaseModel, Field, HttpUrl


class ParseRequest(BaseModel):
    url: HttpUrl
    max_organizations: int = Field(default=100, ge=1, le=300)


class Organization(BaseModel):
    id: str | None = None
    name: str
    category: str | None = None
    address: str | None = None
    phones: list[str] = Field(default_factory=list)
    website: str | None = None
    rating: float | None = None
    yandex_url: str | None = None


class ParseResult(BaseModel):
    source_url: str
    resolved_url: str
    address: str | None
    organizations: list[Organization]
    warnings: list[str] = Field(default_factory=list)
    diagnostics: dict[str, Any] = Field(default_factory=dict)
