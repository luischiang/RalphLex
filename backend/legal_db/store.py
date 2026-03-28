"""SQLite-backed legal reference store with keyword and TF-IDF search."""

import math
import re
import sqlite3
from collections import Counter
from pathlib import Path

import httpx

from backend.legal_db.models import Law, Precedent

DEFAULT_DB_PATH = Path("data/legal_ref.db")

# Stopwords for TF-IDF
_STOPWORDS = frozenset(
    "a an the is was were be been being have has had do does did will would "
    "shall should may might can could of in to for on with at by from as into "
    "through during before after above below between and but or nor not no "
    "this that these those it its he she they them their his her".split()
)


def _tokenize(text: str) -> list[str]:
    """Lowercase and split text into word tokens, removing stopwords."""
    words = re.findall(r"[a-z0-9]+", text.lower())
    return [w for w in words if w not in _STOPWORDS]


class LegalStore:
    """SQLite-backed store for legal precedents and laws."""

    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
            self._init_tables()
        return self._conn

    def _init_tables(self) -> None:
        conn = self._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS precedents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_name TEXT NOT NULL,
                jurisdiction TEXT NOT NULL,
                year INTEGER NOT NULL,
                summary TEXT NOT NULL,
                full_text TEXT NOT NULL,
                tags TEXT NOT NULL DEFAULT '[]',
                outcome TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS laws (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL,
                article TEXT NOT NULL,
                text TEXT NOT NULL,
                jurisdiction TEXT NOT NULL
            );
        """)
        conn.commit()

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    # --- Insert ---

    def insert_precedent(self, p: Precedent) -> int:
        conn = self._get_conn()
        import json

        cur = conn.execute(
            "INSERT INTO precedents "
            "(case_name, jurisdiction, year, summary, full_text, tags, outcome) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                p.case_name,
                p.jurisdiction,
                p.year,
                p.summary,
                p.full_text,
                json.dumps(p.tags),
                p.outcome,
            ),
        )
        conn.commit()
        return cur.lastrowid or 0

    def insert_law(self, law: Law) -> int:
        conn = self._get_conn()
        cur = conn.execute(
            "INSERT INTO laws (code, article, text, jurisdiction) VALUES (?, ?, ?, ?)",
            (law.code, law.article, law.text, law.jurisdiction),
        )
        conn.commit()
        return cur.lastrowid or 0

    # --- Keyword search ---

    def keyword_search_precedents(
        self, query: str, jurisdiction: str | None = None, top_k: int = 5
    ) -> list[Precedent]:
        """Search precedents by keyword matching in case_name, summary, tags, and full_text."""
        conn = self._get_conn()
        import json

        sql = (
            "SELECT * FROM precedents WHERE ("
            "case_name LIKE ? OR summary LIKE ? OR full_text LIKE ? OR tags LIKE ?"
            ")"
        )
        pattern = f"%{query}%"
        params: list[str] = [pattern, pattern, pattern, pattern]
        if jurisdiction:
            sql += " AND jurisdiction = ?"
            params.append(jurisdiction)
        sql += f" LIMIT {top_k * 2}"  # over-fetch for ranking

        rows = conn.execute(sql, params).fetchall()
        results: list[Precedent] = []
        for row in rows:
            tags = json.loads(row["tags"]) if isinstance(row["tags"], str) else row["tags"]
            results.append(
                Precedent(
                    id=row["id"],
                    case_name=row["case_name"],
                    jurisdiction=row["jurisdiction"],
                    year=row["year"],
                    summary=row["summary"],
                    full_text=row["full_text"],
                    tags=tags,
                    outcome=row["outcome"],
                )
            )
        return results[:top_k]

    def keyword_search_laws(
        self, topic: str, jurisdiction: str | None = None, top_k: int = 5
    ) -> list[Law]:
        """Search laws by keyword matching in code, article, and text."""
        conn = self._get_conn()
        sql = "SELECT * FROM laws WHERE (code LIKE ? OR article LIKE ? OR text LIKE ?)"
        pattern = f"%{topic}%"
        params: list[str] = [pattern, pattern, pattern]
        if jurisdiction:
            sql += " AND jurisdiction = ?"
            params.append(jurisdiction)
        sql += f" LIMIT {top_k}"

        rows = conn.execute(sql, params).fetchall()
        return [
            Law(
                id=row["id"],
                code=row["code"],
                article=row["article"],
                text=row["text"],
                jurisdiction=row["jurisdiction"],
            )
            for row in rows
        ]

    # --- TF-IDF search ---

    def tfidf_search_precedents(
        self, query: str, jurisdiction: str | None = None, top_k: int = 5
    ) -> list[Precedent]:
        """TF-IDF similarity search over precedent summaries and full text."""
        conn = self._get_conn()
        import json

        sql = "SELECT * FROM precedents"
        params: list[str] = []
        if jurisdiction:
            sql += " WHERE jurisdiction = ?"
            params.append(jurisdiction)

        rows = conn.execute(sql, params).fetchall()
        if not rows:
            return []

        query_tokens = _tokenize(query)
        if not query_tokens:
            return []

        # Build document token lists
        doc_tokens_list: list[list[str]] = []
        for row in rows:
            text = f"{row['case_name']} {row['summary']} {row['full_text']}"
            doc_tokens_list.append(_tokenize(text))

        # Compute IDF
        n_docs = len(rows)
        idf: dict[str, float] = {}
        for token in set(query_tokens):
            doc_freq = sum(1 for dt in doc_tokens_list if token in dt)
            idf[token] = math.log((n_docs + 1) / (doc_freq + 1)) + 1

        # Score each document
        scored: list[tuple[float, sqlite3.Row]] = []
        for i, row in enumerate(rows):
            doc_counter = Counter(doc_tokens_list[i])
            doc_len = len(doc_tokens_list[i]) or 1
            score = 0.0
            for token in query_tokens:
                tf = doc_counter.get(token, 0) / doc_len
                score += tf * idf.get(token, 0)
            scored.append((score, row))

        scored.sort(key=lambda x: x[0], reverse=True)

        results: list[Precedent] = []
        for score, row in scored[:top_k]:
            if score <= 0:
                break
            tags = json.loads(row["tags"]) if isinstance(row["tags"], str) else row["tags"]
            results.append(
                Precedent(
                    id=row["id"],
                    case_name=row["case_name"],
                    jurisdiction=row["jurisdiction"],
                    year=row["year"],
                    summary=row["summary"],
                    full_text=row["full_text"],
                    tags=tags,
                    outcome=row["outcome"],
                )
            )
        return results

    def tfidf_search_laws(
        self, topic: str, jurisdiction: str | None = None, top_k: int = 5
    ) -> list[Law]:
        """TF-IDF similarity search over law text."""
        conn = self._get_conn()
        sql = "SELECT * FROM laws"
        params: list[str] = []
        if jurisdiction:
            sql += " WHERE jurisdiction = ?"
            params.append(jurisdiction)

        rows = conn.execute(sql, params).fetchall()
        if not rows:
            return []

        query_tokens = _tokenize(topic)
        if not query_tokens:
            return []

        doc_tokens_list: list[list[str]] = []
        for row in rows:
            text = f"{row['code']} {row['article']} {row['text']}"
            doc_tokens_list.append(_tokenize(text))

        n_docs = len(rows)
        idf: dict[str, float] = {}
        for token in set(query_tokens):
            doc_freq = sum(1 for dt in doc_tokens_list if token in dt)
            idf[token] = math.log((n_docs + 1) / (doc_freq + 1)) + 1

        scored: list[tuple[float, sqlite3.Row]] = []
        for i, row in enumerate(rows):
            doc_counter = Counter(doc_tokens_list[i])
            doc_len = len(doc_tokens_list[i]) or 1
            score = 0.0
            for token in query_tokens:
                tf = doc_counter.get(token, 0) / doc_len
                score += tf * idf.get(token, 0)
            scored.append((score, row))

        scored.sort(key=lambda x: x[0], reverse=True)

        results: list[Law] = []
        for score, row in scored[:top_k]:
            if score <= 0:
                break
            results.append(
                Law(
                    id=row["id"],
                    code=row["code"],
                    article=row["article"],
                    text=row["text"],
                    jurisdiction=row["jurisdiction"],
                )
            )
        return results

    # --- Combined retrieval ---

    def retrieve_precedents(
        self, query: str, jurisdiction: str | None = None, top_k: int = 5
    ) -> list[Precedent]:
        """Retrieve precedents using keyword + TF-IDF search, merged and deduplicated."""
        keyword_results = self.keyword_search_precedents(query, jurisdiction, top_k)
        tfidf_results = self.tfidf_search_precedents(query, jurisdiction, top_k)

        seen_ids: set[int] = set()
        merged: list[Precedent] = []
        for p in tfidf_results + keyword_results:
            if p.id not in seen_ids:
                seen_ids.add(p.id)
                merged.append(p)
        return merged[:top_k]

    def retrieve_laws(
        self, topic: str, jurisdiction: str | None = None, top_k: int = 5
    ) -> list[Law]:
        """Retrieve laws using keyword + TF-IDF search, merged and deduplicated."""
        keyword_results = self.keyword_search_laws(topic, jurisdiction, top_k)
        tfidf_results = self.tfidf_search_laws(topic, jurisdiction, top_k)

        seen_ids: set[int] = set()
        merged: list[Law] = []
        for law in tfidf_results + keyword_results:
            if law.id not in seen_ids:
                seen_ids.add(law.id)
                merged.append(law)
        return merged[:top_k]


# --- Internet fallback ---


async def web_search_precedents(
    query: str, jurisdiction: str | None = None, top_k: int = 5
) -> list[dict[str, str]]:
    """Fallback web search for legal precedents when local DB has insufficient results.

    Returns raw search result dicts with keys: title, snippet, url.
    In a real deployment this would hit a legal search API.
    """
    search_query = f"legal precedent {query}"
    if jurisdiction:
        search_query += f" {jurisdiction}"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://api.duckduckgo.com/",
                params={"q": search_query, "format": "json", "no_html": "1"},
            )
            resp.raise_for_status()
            data: dict[str, object] = resp.json()
            results: list[dict[str, str]] = []
            related_topics = data.get("RelatedTopics", [])
            if isinstance(related_topics, list):
                for topic in related_topics[:top_k]:
                    if isinstance(topic, dict) and "Text" in topic:
                        results.append(
                            {
                                "title": str(topic.get("FirstURL", "")),
                                "snippet": str(topic.get("Text", "")),
                                "url": str(topic.get("FirstURL", "")),
                            }
                        )
            return results[:top_k]
    except (httpx.HTTPError, Exception):
        return []


async def retrieve_precedents_with_fallback(
    store: LegalStore,
    query: str,
    jurisdiction: str | None = None,
    top_k: int = 5,
    min_local_results: int = 3,
) -> tuple[list[Precedent], list[dict[str, str]]]:
    """Retrieve precedents from local DB, falling back to web search if insufficient.

    Returns (local_results, web_results). web_results is empty if local DB had enough.
    """
    local = store.retrieve_precedents(query, jurisdiction, top_k)
    web_results: list[dict[str, str]] = []
    if len(local) < min_local_results:
        web_results = await web_search_precedents(query, jurisdiction, top_k)
    return local, web_results


async def retrieve_laws_with_fallback(
    store: LegalStore,
    topic: str,
    jurisdiction: str | None = None,
    top_k: int = 5,
    min_local_results: int = 3,
) -> tuple[list[Law], list[dict[str, str]]]:
    """Retrieve laws from local DB, falling back to web search if insufficient."""
    local = store.retrieve_laws(topic, jurisdiction, top_k)
    web_results: list[dict[str, str]] = []
    if len(local) < min_local_results:
        try:
            search_query = f"law statute {topic}"
            if jurisdiction:
                search_query += f" {jurisdiction}"
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    "https://api.duckduckgo.com/",
                    params={"q": search_query, "format": "json", "no_html": "1"},
                )
                resp.raise_for_status()
                data: dict[str, object] = resp.json()
                related_topics = data.get("RelatedTopics", [])
                if isinstance(related_topics, list):
                    for item in related_topics[:top_k]:
                        if isinstance(item, dict) and "Text" in item:
                            web_results.append(
                                {
                                    "title": str(item.get("FirstURL", "")),
                                    "snippet": str(item.get("Text", "")),
                                    "url": str(item.get("FirstURL", "")),
                                }
                            )
        except (httpx.HTTPError, Exception):
            pass
    return local, web_results
