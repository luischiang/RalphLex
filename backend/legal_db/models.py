"""Pydantic models for legal reference data."""

from pydantic import BaseModel, Field


class Precedent(BaseModel):
    id: int = 0
    case_name: str
    jurisdiction: str
    year: int
    summary: str
    full_text: str
    tags: list[str] = Field(default_factory=list)
    outcome: str


class Law(BaseModel):
    id: int = 0
    code: str
    article: str
    text: str
    jurisdiction: str
