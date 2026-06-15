#!/usr/bin/env python3
"""Ingestion invariants: source detection, extraction, 10-K figures, and the
DocParser/DataCreator feeding the writers' room. No API needed.

    python3 tests/test_ingestion.py
    pytest tests/test_ingestion.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "orchestrator"))

from caseband.ingestion.extract import extract, detect_source_type, strip_html  # noqa: E402
from caseband.bus.local_bus import LocalBus                # noqa: E402
from caseband.conductor import Conductor                   # noqa: E402
from caseband.state_store import StateStore                # noqa: E402
from caseband.rooms import Room                            # noqa: E402
from caseband.agents.intake import DocParser, DataCreator  # noqa: E402

TENK = """ACME CORP FORM 10-K
UNITED STATES SECURITIES AND EXCHANGE COMMISSION
Annual Report Pursuant to Section 13

Item 7. Management's Discussion and Analysis
Total revenue was $4,200 million for fiscal 2025.
Net income of $560 million was reported.
Operating margin improved to 13.3%.
"""

NEWS = """Acme to Acquire Beta Inc for $1.2 billion
(Reuters) - Acme Corp said on Tuesday it would acquire Beta Inc.
The deal values Beta at roughly 8% above its market price.
"""

MEMO = """Marketing Budget Review
The team spent $250,000 last quarter with mixed results.
Leadership wants a clearer return on the next campaign.
"""


def test_detect_source_types():
    assert detect_source_type(TENK) == "10K"
    assert detect_source_type(NEWS) == "news"
    assert detect_source_type(MEMO) == "generic"
    assert detect_source_type("anything", filename="acme-10k.txt") == "10K"


def test_strip_html():
    assert "Hello" in strip_html("<p>Hello <b>world</b></p>")
    assert "<" not in strip_html("<div>plain</div>")


def test_tenk_extracts_canonical_financials():
    doc = extract(TENK)
    assert doc.source_type == "10K" and doc.needs_research is False
    labels = {f["label"]: f["value"] for f in doc.facts}
    assert labels["total revenue"] == 4_200_000_000     # $4,200 million normalized
    assert labels["net income"] == 560_000_000
    assert doc.title.startswith("ACME CORP")


def test_general_path_pulls_numbers_and_flags_research():
    doc = extract(MEMO)
    assert doc.source_type == "generic" and doc.needs_research is True
    vals = [f["value"] for f in doc.facts]
    assert 250000.0 in vals
    news = extract(NEWS)
    assert news.source_type == "news"
    assert any(f["unit"] == "percent" and f["value"] == 8.0 for f in news.facts)


def test_docparser_and_datacreator_feed_writers_room():
    doc_text = TENK
    conductor = Conductor(LocalBus(), StateStore(), room=Room.WRITERS.value)
    parser = DocParser(doc_text)
    # seed meta
    for m in parser.act(conductor.pkg, conductor.room):
        conductor.pkg = __apply(conductor, m)
    assert conductor.pkg.meta["title"].startswith("ACME CORP")
    assert conductor.pkg.meta["source_type"] == "10K"
    # exhibits from extracted facts
    dc = DataCreator(parser.doc)
    for m in dc.act(conductor.pkg, conductor.room):
        conductor.pkg = __apply(conductor, m)
    assert len(conductor.pkg.exhibits) == len(parser.doc.facts) > 0
    assert conductor.pkg.exhibits[0]["unit"] == "usd"


def __apply(conductor, msg):
    from caseband.reducer import apply
    res = apply(conductor.pkg, msg)
    assert res.applied, res.reason
    return res.package


def _run_standalone():
    fns = [v for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"\n{len(fns)} passed")


if __name__ == "__main__":
    _run_standalone()
