import json
import time
import urllib3

import requests
from playwright.sync_api import sync_playwright

from content import (
    extract_from_html,
    extract_pdf_text,
    looks_blocked,
    looks_like_navigation_page,
    looks_like_search_page,
)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)


# Load proxy settings from proxy.json.
def load_proxy() -> str | None:
    try:
        with open("proxy.json", "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return None

    proxy = data.get("proxy")
    if not proxy:
        return None

    username = proxy.get("username")
    password = proxy.get("password")
    hostname = proxy.get("hostname")
    ports = proxy.get("port", {})

    if not username or not password or not hostname:
        return None

    host_only = hostname.split(":")[0]
    http_port = ports.get("http")

    if not http_port:
        return None

    return f"http://{username}:{password}@{host_only}:{http_port}"


# Build requests-compatible proxies dict.
def build_proxies(proxy: str | None) -> dict | None:
    if not proxy:
        return None
    return {"http": proxy, "https": proxy}


# Convert requests-style proxy URL to Playwright proxy config.
def build_playwright_proxy(proxy: str | None) -> dict | None:
    if not proxy:
        return None

    # proxy format: http://user:pass@host:port
    no_scheme = proxy.replace("http://", "", 1)
    creds, hostport = no_scheme.split("@", 1)
    username, password = creds.split(":", 1)

    return {
        "server": f"http://{hostport}",
        "username": username,
        "password": password,
    }


# Final validation for extracted content.
def finalize_content(content: str) -> str:
    content = (content or "").strip()

    lines = content.split("\n")
    lines = [line for line in lines if len(line.strip()) > 40]
    content = "\n".join(lines).strip()

    if len(content.split()) < 30:
        return ""

    if looks_blocked(content):
        return ""
    if looks_like_search_page(content):
        return ""
    if looks_like_navigation_page(content):
        return ""

    return content


# Single HTTP fetch attempt.
def fetch_once_requests(url: str, proxy: str | None) -> dict:
    start = time.perf_counter()
    proxies = build_proxies(proxy)

    try:
        response = requests.get(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept-Language": "en-US,en;q=0.9",
            },
            proxies=proxies,
            timeout=(20, 45),
            allow_redirects=True,
            verify=False,
        )

        content_type = response.headers.get("content-type", "").lower()

        if "application/pdf" in content_type or url.lower().endswith(".pdf"):
            content = extract_pdf_text(response.content)
        else:
            response.encoding = response.encoding or "utf-8"
            content = extract_from_html(response.text)

        content = finalize_content(content)

        return {
            "status_code": response.status_code,
            "content": content,
            "latency": time.perf_counter() - start,
            "method": "requests",
        }

    except Exception:
        return {
            "status_code": 0,
            "content": "",
            "latency": time.perf_counter() - start,
            "method": "requests",
        }


# Browser-based fallback for JS-heavy or blocked pages.
def fetch_once_playwright(url: str, proxy: str | None) -> dict:
    start = time.perf_counter()

    try:
        with sync_playwright() as p:
            launch_args = {"headless": True}

            pw_proxy = build_playwright_proxy(proxy)
            if pw_proxy:
                launch_args["proxy"] = pw_proxy

            browser = p.chromium.launch(**launch_args)
            context = browser.new_context(
                user_agent=USER_AGENT,
                ignore_https_errors=True,
            )
            page = context.new_page()

            page.set_default_navigation_timeout(30000)
            page.set_default_timeout(30000)

            response = page.goto(url, wait_until="domcontentloaded")
            page.wait_for_timeout(2500)

            content_type = ""
            if response:
                headers = response.headers
                content_type = headers.get("content-type", "").lower()

            if "application/pdf" in content_type or url.lower().endswith(".pdf"):
                content = ""
            else:
                html = page.content()
                content = extract_from_html(html)

            content = finalize_content(content)

            context.close()
            browser.close()

            return {
                "status_code": response.status if response else 0,
                "content": content,
                "latency": time.perf_counter() - start,
                "method": "playwright",
            }

    except Exception:
        return {
            "status_code": 0,
            "content": "",
            "latency": time.perf_counter() - start,
            "method": "playwright",
        }


# Choose the better result between two attempts.
def choose_better_result(first: dict, second: dict) -> dict:
    if second.get("content") and not first.get("content"):
        return second
    if first.get("content") and not second.get("content"):
        return first

    if len(second.get("content", "")) > len(first.get("content", "")):
        return second

    if (
        second.get("status_code", 0) in range(200, 400)
        and first.get("status_code", 0) == 0
    ):
        return second

    return first


# Stable scrape strategy:
# 1) requests without proxy
# 2) requests with proxy
# 3) playwright without proxy
# 4) playwright with proxy
def scrape_url(url: str, proxy: str | None) -> dict:
    result_1 = fetch_once_requests(url, proxy=None)
    if result_1["status_code"] in range(200, 400) and result_1["content"]:
        return result_1

    result_2 = fetch_once_requests(url, proxy=proxy)
    best = choose_better_result(result_1, result_2)
    if best["status_code"] in range(200, 400) and best["content"]:
        return best

    result_3 = fetch_once_playwright(url, proxy=None)
    best = choose_better_result(best, result_3)
    if best["status_code"] in range(200, 400) and best["content"]:
        return best

    result_4 = fetch_once_playwright(url, proxy=proxy)
    best = choose_better_result(best, result_4)

    return best
