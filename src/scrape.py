"""Scrape a Substack post and split it into paragraph- and sentence-level chunks.

Integrity rules:
  * Only the author's OWN prose is kept. <blockquote> content (quoted tweets,
    excerpts from system cards, etc.) is excluded -- it is not written by the
    author and would unfairly count as a miss.
  * Figures, captions, and pure-link paragraphs are dropped.

Output: data/chunks.json  with one record per chunk:
  {id, kind: "paragraph"|"sentence", text, n_words, paragraph_id}
plus a top-level meta block (title, author, date, url, source).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

# Abbreviations / tokens whose internal or trailing '.' must NOT end a sentence.
ABBREV = [
    "Mr.", "Mrs.", "Ms.", "Dr.", "Prof.", "Sr.", "Jr.", "St.", "vs.",
    "etc.", "e.g.", "i.e.", "No.", "Fig.", "Inc.", "Ltd.", "Co.", "Vol.",
    "approx.", "cf.", "al.", "U.S.", "U.K.", "Ph.D.", "a.k.a.",
]


def fetch_html(url: str) -> str:
    r = requests.get(url, headers={"User-Agent": UA}, timeout=30)
    r.raise_for_status()
    return r.text


def extract(html: str, container: str | None = None) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    if container:
        body = soup.select_one(container)
    else:
        body = soup.select_one("div.available-content") or soup.select_one("div.body.markup")
    if body is None:
        raise SystemExit(f"Could not find article body container ({container or 'default Substack selectors'}).")

    title_el = soup.select_one("h1.post-title") or soup.find("h1")
    title = title_el.get_text(strip=True) if title_el else ""
    author_el = soup.select_one('a[href*="/profile/"]') or soup.select_one(".profile-hover-card-target a")
    author = author_el.get_text(strip=True) if author_el else ""
    time_el = soup.find("time")
    date = (time_el.get("datetime") or time_el.get_text(strip=True)) if time_el else ""

    # Author's own prose: <p> (and list items) NOT inside a blockquote.
    paras: list[str] = []
    for el in body.find_all(["p", "li"]):
        if el.find_parent("blockquote"):
            continue
        if el.name == "p" and el.find_parent("figure"):
            continue
        # Avoid double-counting: an <li> that wraps a <p> is already captured via
        # that inner <p> (Substack's table-of-contents uses <li><p><a>...).
        if el.name == "li" and el.find("p"):
            continue
        text = el.get_text(" ", strip=True)
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            continue
        # Skip pure-navigation entries (table-of-contents links): the whole element
        # is a single hyperlink, not the author's prose.
        links = el.find_all("a")
        if len(links) == 1 and re.sub(r"\s+", " ", links[0].get_text(" ", strip=True)).strip() == text:
            continue
        paras.append(text)
    return {"title": title, "author": author, "date": date, "paragraphs": paras}


def split_sentences(text: str) -> list[str]:
    """Heuristic sentence splitter that protects abbreviations and decimals
    (e.g. 'Opus 4.8') from being treated as sentence boundaries."""
    DOT = "\x00"
    protected = text
    for ab in ABBREV:
        protected = protected.replace(ab, ab.replace(".", DOT))
    protected = re.sub(r"(\d)\.(\d)", lambda m: m.group(1) + DOT + m.group(2), protected)  # decimals: 4.8
    # Split after . ! ? (optionally followed by a closing quote/paren) then space + capital/quote.
    parts = re.split(r'(?<=[.!?])["”\')\]]?\s+(?=[A-Z"“\'(\[])', protected)
    out = []
    for p in parts:
        p = p.replace("\x00", ".").strip()
        if p:
            out.append(p)
    return out


def n_words(text: str) -> int:
    return len(re.findall(r"\b[\w'-]+\b", text))


def build_chunks(parsed: dict, min_para_words: int, min_sent_words: int) -> list[dict]:
    chunks: list[dict] = []
    pid = 0
    for para in parsed["paragraphs"]:
        if n_words(para) < min_para_words:
            continue
        chunks.append({
            "id": f"p{pid}", "kind": "paragraph", "text": para,
            "n_words": n_words(para), "paragraph_id": pid,
        })
        sid = 0
        for sent in split_sentences(para):
            if n_words(sent) < min_sent_words:
                continue
            chunks.append({
                "id": f"p{pid}s{sid}", "kind": "sentence", "text": sent,
                "n_words": n_words(sent), "paragraph_id": pid,
            })
            sid += 1
        pid += 1
    return chunks


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="https://thezvi.substack.com/p/claude-opus-48-is-honestly-better")
    ap.add_argument("--text-file", default=None,
                    help="Ingest a plain-text article instead of scraping a URL. "
                         "Paragraphs separated by blank lines.")
    ap.add_argument("--title", default="", help="Title to record when using --text-file.")
    ap.add_argument("--author", default="Zvi Mowshowitz",
                    help="Ground-truth author label (for the dataset, not shown to the model).")
    ap.add_argument("--out", default=str(DATA / "chunks.json"))
    ap.add_argument("--html-cache", default=str(DATA / "raw.html"))
    ap.add_argument("--min-para-words", type=int, default=5)
    ap.add_argument("--min-sent-words", type=int, default=1)
    ap.add_argument("--refetch", action="store_true")
    ap.add_argument("--container", default=None,
                    help="CSS selector for the article body (for non-Substack sites, e.g. 'div.entry').")
    args = ap.parse_args()

    DATA.mkdir(exist_ok=True)
    if args.text_file:
        raw = Path(args.text_file).read_text(encoding="utf-8")
        paras = [re.sub(r"\s+", " ", p).strip() for p in re.split(r"\n\s*\n", raw)]
        paras = [p for p in paras if p]
        parsed = {"title": args.title, "author": args.author, "date": "", "paragraphs": paras}
        print(f"ingested {len(paras)} paragraphs from {args.text_file}")
    else:
        cache = Path(args.html_cache)
        if cache.exists() and not args.refetch:
            html = cache.read_text(encoding="utf-8")
            print(f"using cached HTML ({len(html)} bytes)")
        else:
            html = fetch_html(args.url)
            cache.write_text(html, encoding="utf-8")
            print(f"fetched {len(html)} bytes -> {cache}")
        parsed = extract(html, args.container)
    chunks = build_chunks(parsed, args.min_para_words, args.min_sent_words)
    n_para = sum(c["kind"] == "paragraph" for c in chunks)
    n_sent = sum(c["kind"] == "sentence" for c in chunks)

    out = {
        "meta": {
            "title": parsed["title"], "author": args.author,
            "detected_author": parsed["author"], "date": parsed["date"],
            "url": args.url, "n_paragraphs": n_para, "n_sentences": n_sent,
        },
        "chunks": chunks,
    }
    Path(args.out).write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"title:  {parsed['title']}")
    print(f"author: {parsed['author']}  date: {parsed['date']}")
    print(f"paragraphs: {n_para}   sentences: {n_sent}   -> {args.out}")
    print("\nsample paragraph:", next(c['text'] for c in chunks if c['kind']=='paragraph')[:200])
    print("sample sentence: ", next(c['text'] for c in chunks if c['kind']=='sentence')[:160])


if __name__ == "__main__":
    main()
