"""Listing collectors. Each returns dicts:
{source, title, price, year, km, fuel, url, image, text}
"""
from __future__ import annotations

import re
import time
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")
S = requests.Session()
S.headers.update({"User-Agent": UA, "Accept-Language": "is,en;q=0.8"})

PRICE_RE = re.compile(r"(\d{1,3}(?:[.\s ]\d{3})+|\d{4,9})\s*(?:kr|ISK)", re.I)
YEAR_RE = re.compile(r"(?:Árg(?:erð)?\.?|Ár)\s*:?\s*((?:19|20)\d{2})", re.I)
KM_RE = re.compile(r"(?:Akstur|Ekinn|Ekin)\s*:?\s*(\d{1,3}(?:[.\s ]\d{3})+|\d{1,7})\s*(þús|þ\.?\s*km|km)?", re.I)
# Fuel can be a list: "Bensín, Rafmagn" (plug-in hybrid) vs "Rafmagn" (BEV)
FUEL_RE = re.compile(r"(?:Eldsneyti|Orkugjafi)\s*:?\s*((?:[A-Za-zÁÉÍÓÚÝÞÆÖáéíóúýþæöð\-]+)(?:\s*[,/]\s*[A-Za-zÁÉÍÓÚÝÞÆÖáéíóúýþæöð\-]+)*)", re.I)
# Not passenger BEVs even when the fuel field says Rafmagn
NOT_BEV_RE = re.compile(r"plug[\s-]?in|phev|hybrid|hybrid|tvinn|tengil|\bgte\b|\b4xe\b|\b\d{3}e\b|recharge\s*t[68]|"
                        r"golfb[ií]l|hj[oó]lh[yý]s|fellih[yý]s|h[uú]sb[ií]l|hobby|vesp|m[oó]torhj[oó]l|rafhj[oó]l|fjórhj", re.I)
TITLE_YEAR_RE = re.compile(r"\b(20[0-3]\d|19[89]\d)\b")


def get(url, **kw):
    for attempt in range(3):
        try:
            r = S.get(url, timeout=30, **kw)
            if r.status_code == 429:
                time.sleep(5 * (attempt + 1))
                continue
            r.raise_for_status()
            return r
        except requests.RequestException:
            if attempt == 2:
                raise
            time.sleep(2)


def num(s):
    return int(re.sub(r"[^\d]", "", s)) if s and re.search(r"\d", s) else None


def parse_fields(text, title=""):
    """Pull year, km, fuel out of free card/listing text."""
    year = km = fuel = None
    m = YEAR_RE.search(text)
    if m:
        year = int(m.group(1))
    ty = TITLE_YEAR_RE.search(title or "")
    if ty and (year is None or int(ty.group(1)) != year):
        year = int(ty.group(1))  # the seller's own title wins over a mis-set field
    m = KM_RE.search(text)
    if m:
        km = num(m.group(1))
        if km is not None and m.group(2) and "þ" in m.group(2).lower() and km < 1000:
            km *= 1000  # "57 þús km"
    m = FUEL_RE.search(text)
    if m:
        fuel = m.group(1).strip().lower()
    return year, km, fuel


def is_electric(fuel, title=""):
    """Battery-electric only: fuel exactly "Rafmagn", and nothing in the title saying hybrid / not a car."""
    f = (fuel or "").lower().strip(" ,")
    return f == "rafmagn" and not NOT_BEV_RE.search(title or "")


def _cards(html, base, link_rx):
    soup = BeautifulSoup(html, "html.parser")
    out = {}
    for a in soup.find_all("a", href=True):
        href = urljoin(base, a["href"])
        if not re.search(link_rx, href) or href in out:
            continue
        node, price = a, None
        for _ in range(8):
            links = {urljoin(base, x["href"]) for x in node.find_all("a", href=True)
                     if re.search(link_rx, urljoin(base, x["href"]))} if node is not a else {href}
            if len(links) > 1:
                break
            text = node.get_text(" ", strip=True)
            if PRICE_RE.search(text) and YEAR_RE.search(text):
                price = min(num(x) for x in PRICE_RE.findall(text))
                break
            if node.parent is None:
                break
            node = node.parent
        if price is None:
            continue
        text = node.get_text(" ", strip=True)
        h = node.find(["h2", "h3", "h4", "strong"])
        title = a.get_text(" ", strip=True) or (h.get_text(" ", strip=True) if h else "")
        if len(title) < 3 and h:
            title = h.get_text(" ", strip=True)
        src = None
        cover = node.find(attrs={"data-cover": True})
        if cover:
            src = cover["data-cover"]
        else:
            bg = node.find(style=re.compile(r"background-image"))
            m = re.search(r"url\(['\"]?([^'\")]+)", bg["style"]) if bg else None
            img = node.find("img")
            src = m.group(1) if m else (img.get("data-src") or img.get("src")) if img else None
        if src:
            src = re.sub(r"\?d=\d+$", "", src)
            src = urljoin("https:", src) if src.startswith("//") else urljoin(base, src)
            if src.startswith("data:"):
                src = None
        year, km, fuel = parse_fields(text, title)
        out[href] = {"title": title, "price": price, "year": year, "km": km, "fuel": fuel,
                     "url": href, "image": src, "text": text[:600]}
    return list(out.values())


def bland(category, max_pages, log, debug_dir: Path | None = None):
    out = {}
    for page in range(1, max_pages + 1):
        url = category + (f"&page={page}" if page > 1 else "")
        try:
            r = get(url)
        except Exception as e:
            log(f"Bland: failed {url}: {e}")
            break
        if debug_dir is not None and page == 1:
            debug_dir.mkdir(parents=True, exist_ok=True)
            (debug_dir / "bland_page1.html").write_text(r.text, encoding="utf-8")
        cards = _cards(r.text, url, r"/til-solu/.+/\d{5,}/?$")
        if not cards:
            break
        new = 0
        for c in cards:
            if c["url"] not in out:
                c["source"] = "Bland"
                out[c["url"]] = c
                new += 1
        if new == 0:  # past the last page
            break
        time.sleep(1)
    items = list(out.values())
    ev = [c for c in items if is_electric(c["fuel"], c["title"])]
    log(f"Bland: {len(items)} car listings scanned, {len(ev)} electric")
    return items
