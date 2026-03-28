"""Legal reference database module."""

from backend.legal_db.models import Law, Precedent
from backend.legal_db.store import (
    LegalStore,
    retrieve_laws_with_fallback,
    retrieve_precedents_with_fallback,
)

__all__ = [
    "Law",
    "LegalStore",
    "Precedent",
    "retrieve_laws_with_fallback",
    "retrieve_precedents_with_fallback",
]
