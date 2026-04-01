import json

import pandas as pd

from scraper import load_proxy, scrape_url


# Run scraper on all URLs from CSV and write JSONL output.
def run_dataset(input_csv: str, output_jsonl: str) -> None:
    df = pd.read_csv(input_csv)
    proxy = load_proxy()
    total = len(df)

    with open(output_jsonl, "w", encoding="utf-8") as f:
        for index, (_, row) in enumerate(df.iterrows(), start=1):
            url = row["url"]
            print(f"[{index}/{total}] Scraping: {url}")

            result = scrape_url(url, proxy)

            record = {
                "id": int(row["id"]),
                "url": url,
                "content": result["content"],
                "status_code": int(result["status_code"]),
                "latency": round(float(result["latency"]), 3),
            }

            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            f.flush()
