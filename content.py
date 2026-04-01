import re
from io import BytesIO

import trafilatura
from bs4 import BeautifulSoup
from pypdf import PdfReader


# Normalize whitespace and strip surrounding spaces.
def normalize_text(text: str) -> str:
    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


# Detect common block-page signals.
def looks_blocked(text: str) -> bool:
    lowered = (text or "").lower()
    blocked_signs = [
        "captcha",
        "verify you are human",
        "access denied",
        "enable javascript",
        "cloudflare",
        "unusual traffic",
        "robot or human",
        "checking your browser",
        "press and hold",
    ]
    return any(sign in lowered for sign in blocked_signs)


# Detect common search-result pages.
def looks_like_search_page(text: str) -> bool:
    lowered = (text or "").lower()
    search_page_hints = [
        "search results",
        "duckduckgo",
        "results for",
        "did not match any documents",
        "google search",
        "bing",
        "yahoo search",
        "search the web",
    ]
    return any(hint in lowered for hint in search_page_hints)


# Detect navigation-heavy pages.
def looks_like_navigation_page(text: str) -> bool:
    lowered = (text or "").lower()
    keywords = [
        "home",
        "about us",
        "contact us",
        "privacy policy",
        "terms of use",
        "all rights reserved",
        "cookie policy",
        "subscribe",
        "sign in",
        "log in",
        "skip to content",
    ]
    hits = sum(keyword in lowered for keyword in keywords)
    return hits >= 4


# Remove noisy patterns and short lie_text lines.
def remove_noisy_lines(text: str) -> str:
    noisy_patterns = [
        r"^home$",
        r"^menu$",
        r"^search$",
        r"^read more$",
        r"^subscribe$",
        r"^sign in$",
        r"^log in$",
        r"^privacy policy$",
        r"^terms of use$",
        r"^all rights reserved$",
        r"^cookie",
        r"^accept",
        r"^skip to",
        r"^share$",
        r"^print$",
    ]

    parts = re.split(r"[\n\r]+|(?<=[.!?])\s{2,}", text)
    cleaned = []

    for part in parts:
        line = normalize_text(part)
        if not line:
            continue

        lowered = line.lower()

        if any(re.search(pattern, lowered) for pattern in noisy_patterns):
            continue

        if len(line) < 35 and any(
            token in lowered
            for token in [
                "home",
                "menu",
                "search",
                "login",
                "sign in",
                "subscribe",
                "cookie",
                "privacy",
                "terms",
                "contact",
            ]
        ):
            continue

        cleaned.append(line)

    return "\n".join(cleaned)


# Remove repeated adjacent lines and near-duplicates.
def deduplicate_lines(text: str) -> str:
    lines = [normalize_text(line) for line in text.split("\n") if normalize_text(line)]
    result = []
    seen = set()

    for line in lines:
        key = line.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(line)

    return "\n".join(result)


# Trim leading boilerplate before likely content start.
def trim_leading_boilerplate(text: str) -> str:
    lines = [line for line in text.split("\n") if line.strip()]
    if not lines:
        return ""

    start_markers = [
        "abstract",
        "overview",
        "introduction",
        "summary",
    ]

    for i, line in enumerate(lines[:15]):
        lowered = line.lower()
        if any(marker in lowered for marker in start_markers):
            return "\n".join(lines[i:])

    return "\n".join(lines)


# Trim common trailing boilerplate.
def trim_trailing_boilerplate(text: str) -> str:
    lines = [line for line in text.split("\n") if line.strip()]
    if not lines:
        return ""

    trailing_patterns = [
        r"privacy policy",
        r"terms of use",
        r"all rights reserved",
        r"subscribe",
        r"cookie policy",
        r"related articles",
        r"recommended",
        r"share this article",
        r"follow us",
        r"newsletter",
    ]

    cut_index = len(lines)

    for i, line in enumerate(lines):
        lowered = line.lower()
        if any(re.search(pattern, lowered) for pattern in trailing_patterns):
            cut_index = min(cut_index, i)

    return "\n".join(lines[:cut_index]).strip()


# Final cleanup and filtering.
def postprocess_text(text: str) -> str:
    text = normalize_text(text)
    if not text:
        return ""

    text = remove_noisy_lines(text)
    text = deduplicate_lines(text)
    text = trim_leading_boilerplate(text)
    text = trim_trailing_boilerplate(text)
    text = normalize_text(text)

    if looks_blocked(text):
        return ""
    if looks_like_search_page(text):
        return ""
    if looks_like_navigation_page(text):
        return ""

    return text


# Try extracting from structured page sections first.
def extract_structured_section(soup: BeautifulSoup) -> str:
    candidates = []

    for tag_name in ["article", "main"]:
        for section in soup.find_all(tag_name):
            text = normalize_text(section.get_text(" ", strip=True))
            if len(text.split()) > 60:
                candidates.append(text)

    for selector in [
        {"name": "div", "attrs": {"role": "main"}},
        {"name": "section", "attrs": {"role": "main"}},
    ]:
        for section in soup.find_all(selector["name"], attrs=selector["attrs"]):
            text = normalize_text(section.get_text(" ", strip=True))
            if len(text.split()) > 60:
                candidates.append(text)

    if not candidates:
        return ""

    candidates.sort(key=lambda x: len(x.split()), reverse=True)
    return postprocess_text(candidates[0])


# Extract main readable text from HTML.
def extract_from_html(html: str) -> str:
    extracted = trafilatura.extract(
        html,
        include_comments=False,
        include_tables=False,
        favor_precision=True,
        deduplicate=True,
        output_format="txt",
    )

    if extracted and len(extracted.split()) > 50:
        cleaned = postprocess_text(extracted)
        if cleaned:
            return cleaned

    soup = BeautifulSoup(html, "lxml")

    structured_text = extract_structured_section(soup)
    if structured_text:
        return structured_text

    for tag in soup(["script", "style", "noscript", "svg", "canvas", "form", "iframe"]):
        tag.decompose()

    for tag in soup.find_all(["nav", "footer", "header", "aside"]):
        tag.decompose()

    for selector in [
        "[class*='cookie']",
        "[id*='cookie']",
        "[class*='consent']",
        "[id*='consent']",
        "[class*='banner']",
        "[class*='footer']",
        "[class*='header']",
        "[class*='nav']",
        "[class*='menu']",
        "[class*='sidebar']",
        "[class*='related']",
        "[class*='recommend']",
        "[class*='breadcrumb']",
        "[class*='social']",
        "[class*='share']",
    ]:
        for element in soup.select(selector):
            element.decompose()

    fallback_text = soup.get_text("\n", strip=True)
    return postprocess_text(fallback_text)


# Extract text from PDF bytes.
def extract_pdf_text(pdf_bytes: bytes) -> str:
    reader = PdfReader(BytesIO(pdf_bytes))
    texts = []

    for page in reader.pages:
        txt = page.extract_text() or ""
        if txt.strip():
            texts.append(txt)

    return postprocess_text("\n".join(texts))
