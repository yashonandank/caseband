"""Ingestion (AGENT_SPECS §0): turn an uploaded document into a structured
SourceDoc the writers room can build on. General path (txt/HTML) is default; a
10-K extractor kicks in only when an SEC filing is detected. PDF/DOCX loaders plug
in behind the same SourceDoc contract."""
