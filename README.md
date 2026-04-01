# Scraping Quality Benchmark

Hybrid web scraping system combining lightweight HTTP extraction and browser-based rendering (Playwright).

## Approach

The system uses two scraping strategies:

1. Lightweight HTTP fetch (requests)
2. Browser-based rendering (Playwright)

A fallback mechanism ensures high success rate and robustness.

Content extraction is performed using Trafilatura and heuristic filtering to maximize truth_text and minimize lie_text.

## Features

- HTML and PDF support
- Proxy integration
- Playwright fallback for dynamic pages
- Content cleaning and deduplication

## How to Run

```bash
pip install -r requirements.txt
playwright install chromium
python main.py
```

## Files

- train_results.jsonl — training results
- test_results.jsonl — test results
- notebook.ipynb — analysis and benchmarking
- scraping_quality_benchmark.pdf — summary

## Notes

Some pages may still contain residual lie_text or be partially blocked due to anti-bot protections.
