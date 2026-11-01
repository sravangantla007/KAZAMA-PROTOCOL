# DECISIONS.md — Kazama Protocol / Digital Dark Spot

This file records all deviations from or assumptions made during implementation.

| # | Phase | Decision | Rationale |
|---|---|---|---|
| 1 | 1 | `pdfplumber` primary; `pypdf` fallback for PDF parsing | Spec §3 Module 1 |
| 2 | 1 | `NullProvider` built first; `TavilyProvider` implemented as real provider | Tavily chosen per user preference |
| 3 | 1 | `reportlab` used in tests to generate in-memory PDFs | Avoids shipping binary fixture |
| 4 | 0 | Anthropic is the one real LLM provider; others raise `NotImplementedError` | Spec §0 Rule 5 |
| 5 | 0 | `TAVILY_API_KEY` added to `.env.example` alongside `SEARCH_API_KEY` | Tavily is the implemented search provider |
| 6 | 3 | Gemini implemented as primary LLM provider (`gemini-2.5-flash` / `gemini-3.5-flash`) | Fast structured JSON output, low latency, 1M context |
| 7 | 3 | Prompt budget raised from 60k to 500k characters | Gemini 1M-token context comfortably fits all 12 ingested sources without dropping any |
| 8 | 2 | Dual AI Detection: pure-Python artifact scanner + Gemini Forensics Classifier | Instant offline checks (0ms) catch smoking guns at 0.95+; Gemini provides deep reasoning (0.99) without paid Hugging Face credits |
