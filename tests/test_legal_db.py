"""Tests for the legal reference database module."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.legal_db.models import Law, Precedent
from backend.legal_db.seed import SAMPLE_LAWS, SAMPLE_PRECEDENTS, seed_database
from backend.legal_db.store import (
    LegalStore,
    retrieve_laws_with_fallback,
    retrieve_precedents_with_fallback,
    web_search_precedents,
)


@pytest.fixture
def store(tmp_path):
    """Create a LegalStore with a temporary database."""
    db_path = tmp_path / "test_legal.db"
    s = LegalStore(db_path=db_path)
    yield s
    s.close()


@pytest.fixture
def seeded_store(tmp_path):
    """Create a seeded LegalStore with sample data."""
    db_path = tmp_path / "test_legal_seeded.db"
    s = seed_database(db_path=db_path)
    yield s
    s.close()


# --- Model tests ---


class TestModels:
    def test_precedent_creation(self):
        p = Precedent(
            case_name="Test Case",
            jurisdiction="US",
            year=2020,
            summary="A test case",
            full_text="Full text of the test case",
            tags=["test", "example"],
            outcome="Plaintiff wins",
        )
        assert p.case_name == "Test Case"
        assert p.tags == ["test", "example"]

    def test_law_creation(self):
        law = Law(
            code="TestCode",
            article="Article 1",
            text="Test law text",
            jurisdiction="US",
        )
        assert law.code == "TestCode"
        assert law.jurisdiction == "US"

    def test_precedent_default_tags(self):
        p = Precedent(
            case_name="Test",
            jurisdiction="US",
            year=2020,
            summary="Summary",
            full_text="Text",
            outcome="Outcome",
        )
        assert p.tags == []


# --- Store tests ---


class TestLegalStore:
    def test_insert_and_retrieve_precedent(self, store):
        p = Precedent(
            case_name="Test v Test",
            jurisdiction="US",
            year=2020,
            summary="Contract breach case",
            full_text="The defendant breached the contract by failing to deliver goods.",
            tags=["contract", "breach"],
            outcome="Plaintiff awarded damages",
        )
        pid = store.insert_precedent(p)
        assert pid > 0

    def test_insert_and_retrieve_law(self, store):
        law = Law(
            code="TestCode",
            article="Section 1",
            text="All parties must act in good faith.",
            jurisdiction="US",
        )
        lid = store.insert_law(law)
        assert lid > 0

    def test_keyword_search_precedents(self, seeded_store):
        results = seeded_store.keyword_search_precedents("negligence")
        assert len(results) > 0
        names = [r.case_name for r in results]
        assert any("Donoghue" in n for n in names)

    def test_keyword_search_precedents_with_jurisdiction(self, seeded_store):
        results = seeded_store.keyword_search_precedents(
            "constitutional", jurisdiction="United States"
        )
        assert len(results) > 0
        for r in results:
            assert r.jurisdiction == "United States"

    def test_keyword_search_laws(self, seeded_store):
        results = seeded_store.keyword_search_laws("tort")
        assert len(results) > 0

    def test_keyword_search_laws_with_jurisdiction(self, seeded_store):
        results = seeded_store.keyword_search_laws("quality", jurisdiction="United Kingdom")
        assert len(results) > 0
        for r in results:
            assert r.jurisdiction == "United Kingdom"

    def test_tfidf_search_precedents(self, seeded_store):
        results = seeded_store.tfidf_search_precedents("contract damages foreseeability")
        assert len(results) > 0
        # Hadley v Baxendale should rank high for this query
        top_names = [r.case_name for r in results[:3]]
        assert any("Hadley" in n for n in top_names)

    def test_tfidf_search_precedents_with_jurisdiction(self, seeded_store):
        results = seeded_store.tfidf_search_precedents(
            "duty of care negligence", jurisdiction="United Kingdom"
        )
        assert len(results) > 0
        for r in results:
            assert r.jurisdiction == "United Kingdom"

    def test_tfidf_search_laws(self, seeded_store):
        results = seeded_store.tfidf_search_laws("product liability defective")
        assert len(results) > 0

    def test_tfidf_search_empty_query(self, seeded_store):
        # Stopwords-only query should return empty
        results = seeded_store.tfidf_search_precedents("the a an")
        assert results == []

    def test_retrieve_precedents_merged(self, seeded_store):
        """retrieve_precedents combines keyword + TF-IDF and deduplicates."""
        results = seeded_store.retrieve_precedents("contract breach damages")
        assert len(results) > 0
        ids = [r.id for r in results]
        assert len(ids) == len(set(ids)), "Results should be deduplicated"

    def test_retrieve_laws_merged(self, seeded_store):
        """retrieve_laws combines keyword + TF-IDF and deduplicates."""
        results = seeded_store.retrieve_laws("liability damages")
        assert len(results) > 0
        ids = [r.id for r in results]
        assert len(ids) == len(set(ids)), "Results should be deduplicated"

    def test_retrieve_precedents_top_k(self, seeded_store):
        results = seeded_store.retrieve_precedents("law", top_k=3)
        assert len(results) <= 3

    def test_empty_db_returns_empty(self, store):
        results = store.retrieve_precedents("anything")
        assert results == []
        results_laws = store.retrieve_laws("anything")
        assert results_laws == []

    def test_close_and_reopen(self, tmp_path):
        db_path = tmp_path / "reopen.db"
        s = LegalStore(db_path=db_path)
        s.insert_precedent(
            Precedent(
                case_name="Persist Test",
                jurisdiction="US",
                year=2020,
                summary="Test persistence",
                full_text="Full text",
                tags=["test"],
                outcome="Pass",
            )
        )
        s.close()

        s2 = LegalStore(db_path=db_path)
        results = s2.keyword_search_precedents("Persist")
        assert len(results) == 1
        assert results[0].case_name == "Persist Test"
        s2.close()


# --- Seed tests ---


class TestSeed:
    def test_seed_creates_data(self, seeded_store):
        conn = seeded_store._get_conn()
        p_count: int = conn.execute("SELECT COUNT(*) FROM precedents").fetchone()[0]
        l_count: int = conn.execute("SELECT COUNT(*) FROM laws").fetchone()[0]
        assert p_count == len(SAMPLE_PRECEDENTS)
        assert l_count == len(SAMPLE_LAWS)

    def test_seed_data_is_searchable(self, seeded_store):
        results = seeded_store.keyword_search_precedents("Donoghue")
        assert len(results) == 1
        assert results[0].case_name == "Donoghue v Stevenson"

    def test_seed_tags_are_lists(self, seeded_store):
        results = seeded_store.keyword_search_precedents("Hadley")
        assert len(results) == 1
        assert isinstance(results[0].tags, list)
        assert "contract" in results[0].tags


# --- Fallback tests ---


def _make_httpx_mock(json_data: dict[str, object]) -> MagicMock:
    """Create a mock httpx.AsyncClient that returns json_data from GET."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = json_data
    mock_resp.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.get.return_value = mock_resp

    mock_cls = MagicMock()
    mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
    mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
    return mock_cls


class TestFallback:
    async def test_fallback_triggers_when_insufficient_local(self, store):
        """Web search fallback triggers when local results < min_local_results."""
        mock_cls = _make_httpx_mock(
            {"RelatedTopics": [{"Text": "Some legal result", "FirstURL": "https://example.com/1"}]}
        )
        with patch("backend.legal_db.store.httpx.AsyncClient", mock_cls):
            local, web = await retrieve_precedents_with_fallback(
                store, "contract breach", min_local_results=3
            )
            assert local == []  # empty store
            assert len(web) > 0

    async def test_no_fallback_when_sufficient_local(self, seeded_store):
        """Web search does NOT trigger when local results >= min_local_results."""
        mock_cls = _make_httpx_mock({"RelatedTopics": []})
        with patch("backend.legal_db.store.httpx.AsyncClient", mock_cls):
            local, web = await retrieve_precedents_with_fallback(
                seeded_store, "contract", min_local_results=1
            )
            assert len(local) >= 1
            assert web == []

    async def test_fallback_handles_http_error(self, store):
        """Fallback gracefully handles HTTP errors."""
        import httpx as httpx_mod

        mock_client = AsyncMock()
        mock_client.get.side_effect = httpx_mod.HTTPError("timeout")
        mock_cls = MagicMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("backend.legal_db.store.httpx.AsyncClient", mock_cls):
            local, web = await retrieve_precedents_with_fallback(
                store, "anything", min_local_results=3
            )
            assert web == []

    async def test_web_search_precedents_returns_results(self):
        """web_search_precedents parses DuckDuckGo-style response."""
        mock_cls = _make_httpx_mock(
            {
                "RelatedTopics": [
                    {"Text": "Result one", "FirstURL": "https://example.com/1"},
                    {"Text": "Result two", "FirstURL": "https://example.com/2"},
                ]
            }
        )
        with patch("backend.legal_db.store.httpx.AsyncClient", mock_cls):
            results = await web_search_precedents("test query")
            assert len(results) == 2
            assert results[0]["snippet"] == "Result one"

    async def test_laws_fallback_triggers(self, store):
        """Laws fallback triggers when local results insufficient."""
        mock_cls = _make_httpx_mock(
            {"RelatedTopics": [{"Text": "Law result", "FirstURL": "https://example.com/law1"}]}
        )
        with patch("backend.legal_db.store.httpx.AsyncClient", mock_cls):
            local, web = await retrieve_laws_with_fallback(store, "employment", min_local_results=3)
            assert local == []
            assert len(web) > 0
