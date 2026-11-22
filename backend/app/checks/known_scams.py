"""Known-scam memory (Phase 10): approved scam messages, and "does this new SMS look like one of them?".

How alike two messages are is measured with letter patterns (3-5 letter pieces, cosine similarity), not
with MIRA's vectors: a test on the 28 real scams showed MIRA's vectors rate normal bank/eSewa messages as
very similar to scams (up to 0.94), while letter patterns kept normal messages at <= 0.20 and re-worded
scams at >= 0.42. The cut-offs are in scoring.json ("known_scam").

Before comparing, links are replaced by one word (link checks already judge links) and digits by 0
(amounts and dates change between copies). Messages with too little text left are not compared.
Only masked text is stored."""
from __future__ import annotations

import csv
import logging
import math
import re
import threading
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from ..db import KnownScam
from .textprep import extract_urls, mask_pii

log = logging.getLogger("checkscam.known_scams")

METHOD = "char3-5"  # saved in known_scams.embedding_model
MIN_TEXT = 20  # letters/digits left after removing links; shorter messages are not compared
DUPLICATE = 0.95  # adding a message this similar to an existing entry is skipped
_GRAM_SIZES = (3, 4, 5)
_PLACEHOLDER = re.compile(r"<[A-Z_]+(?: \d+)?>")  # <PHONE>, <LINK 1>, <NUMBER>...
_KEEP = re.compile(r"[^\w\s]", re.UNICODE)


def normalize(text: str) -> str:
    """Lower case, links -> 'link', placeholders/digits -> '0', no symbols or emoji, single spaces."""
    t = text
    for url in sorted(extract_urls(t), key=len, reverse=True):
        t = t.replace(url, " link ")
    t = _PLACEHOLDER.sub(" 0 ", t)
    t = re.sub(r"\d+([.,]\d+)*", "0", t.lower())
    t = _KEEP.sub(" ", t)
    return re.sub(r"\s+", " ", t).strip()


def _content_length(norm: str) -> int:
    return len(re.sub(r"\blink\b|[\s0]", "", norm))


def grams(text: str) -> Counter | None:
    """Letter-piece counts of a message, or None when too little text is left to compare."""
    norm = normalize(text)
    if _content_length(norm) < MIN_TEXT:
        return None
    return Counter(norm[i:i + n] for n in _GRAM_SIZES for i in range(len(norm) - n + 1))


def _norm(g: Counter) -> float:
    return math.sqrt(sum(v * v for v in g.values())) or 1.0


def similarity(a: Counter, b: Counter, norm_a: float | None = None, norm_b: float | None = None) -> float:
    if len(a) > len(b):
        a, b, norm_a, norm_b = b, a, norm_b, norm_a
    dot = sum(v * b.get(k, 0) for k, v in a.items())
    return dot / ((norm_a or _norm(a)) * (norm_b or _norm(b)))


@dataclass
class Match:
    id: int
    similarity: float
    category: str


@dataclass
class _Entry:
    id: int
    category: str
    grams: Counter
    norm: float


class KnownScamMemory:
    """All known scams, kept in memory for fast matching and loaded from the database on first use."""

    def __init__(self, sessions: sessionmaker):
        self._sessions = sessions
        self._entries: list[_Entry] | None = None
        self._lock = threading.Lock()

    def _load(self) -> list[_Entry]:
        with self._lock:
            if self._entries is None:
                with self._sessions() as db:
                    rows = db.execute(select(KnownScam.id, KnownScam.text, KnownScam.category)).all()
                entries = []
                for row_id, text, category in rows:
                    g = grams(text)
                    if g:
                        entries.append(_Entry(row_id, category, g, _norm(g)))
                self._entries = entries
                log.info("Known-scam memory loaded: %d entries", len(entries))
            return self._entries

    def reload(self) -> None:
        with self._lock:
            self._entries = None

    def __len__(self) -> int:
        return len(self._load())

    def best_match(self, text: str) -> Match | None:
        """The most similar known scam (any similarity), or None if the message is too short / memory empty."""
        g = grams(text)
        if g is None:
            return None
        n = _norm(g)
        best: Match | None = None
        for e in self._load():
            s = similarity(g, e.grams, n, e.norm)
            if best is None or s > best.similarity:
                best = Match(e.id, round(s, 3), e.category)
        return best

    def add(self, db: Session, text: str, category: str = "", source: str = "collected") -> int | None:
        """Masks and stores one scam. Returns its id, or None if it is too short or already known."""
        masked = mask_pii(text)
        g = grams(masked)
        if g is None:
            return None
        hit = self.best_match(masked)
        if hit and hit.similarity >= DUPLICATE:
            return None
        row = KnownScam(text=masked, category=category[:64], source=source, embedding=None, embedding_model=METHOD)
        db.add(row)
        db.commit()
        entries = self._load()
        with self._lock:
            entries.append(_Entry(row.id, row.category, g, _norm(g)))
        return row.id


def seed_from_csv(db: Session, memory: KnownScamMemory, path: str | Path) -> tuple[int, int]:
    """Adds the rows labelled 'scam' from a data file (text,label,...). Returns (added, skipped)."""
    added = skipped = 0
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("label") != "scam":
                continue
            if memory.add(db, row["text"], row.get("category", ""), source="collected") is None:
                skipped += 1
            else:
                added += 1
    return added, skipped
