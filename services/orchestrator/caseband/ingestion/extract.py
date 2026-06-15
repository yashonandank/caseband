"""Document detection + extraction. Deterministic (regex/heuristics; no LLM): the
same upload always yields the same SourceDoc, so authoring is reproducible.

  detect_source_type(text, filename) -> "10K" | "news" | "generic"
  extract(text, filename)            -> SourceDoc(title, source_type, needs_research,
                                                  sections, facts)

facts are labeled numbers pulled from the text (currency / percentages, plus the
canonical 10-K line items when a filing is detected) — raw material for exhibits
and the outcome_model. HTML is stripped first; PDF/DOCX loaders feed plain text in
behind the same contract."""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any

_TENK_MARKERS = (
    "form 10-k", "securities and exchange commission",
    "annual report pursuant to section 13", "item 7. management",
    "item 8. financial statements",
)
_NEWS_MARKERS = ("(reuters)", "(ap)", "(bloomberg)", "—reporting by", "press release")
_MULT = {"billion": 1_000_000_000, "bn": 1_000_000_000,
         "million": 1_000_000, "m": 1_000_000, "thousand": 1_000, "k": 1_000}
# Canonical 10-K line items worth extracting exactly.
_TENK_LINES = ("total revenues", "total revenue", "net revenues", "net sales",
               "net income", "operating income", "total assets", "gross profit")


@dataclass
class SourceDoc:
    title: str
    source_type: str
    needs_research: bool
    sections: list[str] = field(default_factory=list)
    facts: list[dict[str, Any]] = field(default_factory=list)


class _Stripper(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []

    def handle_data(self, data: str) -> None:
        self._chunks.append(data)

    def text(self) -> str:
        return "".join(self._chunks)


def strip_html(text: str) -> str:
    if "<" not in text or ">" not in text:
        return text
    p = _Stripper()
    p.feed(text)
    return p.text()


def _num(raw: str, unit: str | None) -> float:
    val = float(raw.replace(",", ""))
    if unit:
        val *= _MULT.get(unit.lower(), 1)
    return val


def detect_source_type(text: str, filename: str | None = None) -> str:
    low = text.lower()
    name = (filename or "").lower()
    if "10-k" in name or "10k" in name or any(m in low for m in _TENK_MARKERS):
        return "10K"
    if any(m in low for m in _NEWS_MARKERS):
        return "news"
    return "generic"


def _title(text: str) -> str:
    for line in text.splitlines():
        s = line.strip()
        if 3 <= len(s) <= 120:
            return s
    flat = " ".join(text.split())
    return (flat[:80] + "…") if len(flat) > 80 else (flat or "Untitled case")


def _sections(text: str) -> list[str]:
    return [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]


_CURRENCY = re.compile(
    r"([A-Za-z][A-Za-z .'-]{2,40}?)\D{0,8}\$\s*([\d,]+(?:\.\d+)?)\s*(billion|million|thousand|bn|m|k)?",
    re.IGNORECASE)
_PERCENT = re.compile(r"([A-Za-z][A-Za-z .'-]{2,40}?)\D{0,8}([\d.]+)\s*%", re.IGNORECASE)


def _general_facts(text: str, limit: int = 12) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    for m in _CURRENCY.finditer(text):
        facts.append({"label": m.group(1).strip().lower(), "value": _num(m.group(2), m.group(3)),
                      "unit": "usd", "raw": m.group(0).strip()})
    for m in _PERCENT.finditer(text):
        facts.append({"label": m.group(1).strip().lower(), "value": float(m.group(2)),
                      "unit": "percent", "raw": m.group(0).strip()})
    return facts[:limit]


def _tenk_facts(text: str) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    for line in _TENK_LINES:
        m = re.search(line + r"\D{0,40}\$?\s*([\d,]+(?:\.\d+)?)\s*(billion|million|thousand)?",
                      text, re.IGNORECASE)
        if m:
            facts.append({"label": line, "value": _num(m.group(1), m.group(2)),
                          "unit": "usd", "raw": m.group(0).strip()})
    return facts


def extract(text: str, filename: str | None = None) -> SourceDoc:
    clean = strip_html(text)
    source_type = detect_source_type(clean, filename)
    facts = _tenk_facts(clean) if source_type == "10K" else _general_facts(clean)
    # A 10-K is self-contained; news/generic usually need external context first.
    needs_research = source_type != "10K"
    return SourceDoc(title=_title(clean), source_type=source_type,
                     needs_research=needs_research, sections=_sections(clean), facts=facts)
