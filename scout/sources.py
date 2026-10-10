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
# "Ár 2020", "Árg. 2020", "Árgerð (nýskráð): 05/2022"
YEAR_RE = re.compile(r"(?:Árg(?:erð)?\.?|Ár)\s*(?:\([^)]*\))?\s*:?\s*(?:\d{1,2}/)?((?:19|20)\d{2})", re.I)
KM_RE = re.compile(r"(?:Akstur|Ekinn|Ekin)\s*(?:\(km\))?\s*:?\s*(\d{1,3}(?:[.\s ]\d{3})+|\d{1,7})\s*(þús|þ\.?\s*km|km)?", re.I)
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


# --- Dealer stock pages (new and used) ---------------------------------------------

SKIP_LABEL_RE = re.compile(r"(afsl[aá]ttur|rafb[ií]lastyrkur|styrkur)\s*:?\s*-?\s*$", re.I)
PHEV_RE = re.compile(r"(bens[ií]n|d[ií]s[ei]l)\s*/\s*rafmagn|rafmagn\s*/\s*(bens|d[ií]s)|plug[\s-]?in|hybrid|phev", re.I)


def card_prices(text):
    """All prices on a card except discount and grant amounts ("Afsláttur -1.890.000 kr.", "Rafbílastyrkur 500.000 kr.")."""
    out = []
    for m in PRICE_RE.finditer(text):
        if SKIP_LABEL_RE.search(text[max(0, m.start() - 25):m.start()]):
            continue
        v = num(m.group(1))
        if v and v >= 500000:
            out.append(v)
    return out


NOT_PHOTO_RE = re.compile(r"overlay|logo|badge|icon|sprite|placeholder|\.svg(\?|$)|strevda", re.I)


def _image(node, base):
    """First real car photo in the node — skips promo overlays, logos and icons."""
    cands = []
    cover = node.find(attrs={"data-cover": True})
    if cover:
        cands.append(cover["data-cover"])
    for el in node.find_all(style=re.compile(r"background-image")):
        m = re.search(r"url\(['\"]?([^'\")]+)", el["style"])
        if m:
            cands.append(m.group(1))
    for img in node.find_all("img"):
        src = (img.get("data-src") or img.get("src") or "").split(" ")[0]
        if (not src or src.startswith("data:")) and img.get("srcset"):
            src = img["srcset"].split(",")[0].split()[0]
        cands.append(src)
    for src in cands:
        if src and not src.startswith("data:") and not NOT_PHOTO_RE.search(src):
            return urljoin("https:", src) if src.startswith("//") else urljoin(base, src)
    return None


def _card_image(node, a, href, base, link_rx):
    """The photo often sits beside the text block (Hekla: imageWrap next to content), so climb a
    few more levels while we're still inside this one car's card."""
    for _ in range(4):
        img = _image(node, base)
        if img:
            return img
        parent = node.parent
        if parent is None:
            return None
        links = {urljoin(base, x["href"]).split("#")[0] for x in parent.find_all("a", href=True)
                 if re.search(link_rx, urljoin(base, x["href"]))}
        if len(links) > 1:
            return None
        node = parent
    return None


def dealer_cards(html, base, link_rx, source, new, electric_rx=None):
    soup = BeautifulSoup(html, "html.parser")
    out = {}
    for a in soup.find_all("a", href=True):
        href = urljoin(base, a["href"]).split("#")[0]
        if not re.search(link_rx, href) or href in out:
            continue
        node, prices = a, []
        for _ in range(8):
            links = {urljoin(base, x["href"]).split("#")[0] for x in node.find_all("a", href=True)
                     if re.search(link_rx, urljoin(base, x["href"]))} if node is not a else {href}
            if len(links) > 1:
                break
            prices = card_prices(node.get_text(" ", strip=True))
            if prices:
                break
            if node.parent is None:
                break
            node = node.parent
        if not prices:
            continue
        text = node.get_text(" ", strip=True)
        names = [x.get_text(" ", strip=True) for x in node.find_all("a", href=True)
                 if urljoin(base, x["href"]).split("#")[0] == href]
        h = node.find(["h2", "h3", "h4"])
        title = max(names + ([h.get_text(" ", strip=True)] if h else []), key=len, default="")
        year, km, fuel = parse_fields(text, title)
        electric = (bool(re.search(r"\brafmagn\b|100\s*%\s*raf", text, re.I))
                    or bool(electric_rx and re.search(electric_rx, text, re.I))) and not PHEV_RE.search(text + " " + title)
        out[href] = {"source": source, "title": title, "price": min(prices), "list_price": max(prices),
                     "grant_applied": bool(re.search(r"styrk", text, re.I)) and len(prices) > 1,
                     "year": year, "km": km, "fuel": "rafmagn" if electric else (fuel or ""),
                     "url": href, "image": _card_image(node, a, href, base, link_rx), "text": text[:600], "new": new}
    return list(out.values())


def dealer(name, url_tmpl, link_rx, new, max_pages, log, electric_rx=None):
    out = {}
    for page in range(1, max_pages + 1):
        url = url_tmpl.format(page=page)
        try:
            r = get(url)
        except Exception as e:
            if page == 1:
                raise
            break
        if page == 1:
            dbg = Path(__file__).resolve().parent.parent / "data" / "debug"
            dbg.mkdir(parents=True, exist_ok=True)
            (dbg / (re.sub(r"\W+", "_", name).strip("_").lower() + "_page1.html")).write_text(r.text, encoding="utf-8")
        cards = dealer_cards(r.text, url, link_rx, name, new, electric_rx)
        fresh = [c for c in cards if c["url"] not in out]
        if not fresh:
            break
        for c in fresh:
            out[c["url"]] = c
        time.sleep(1)
    items = list(out.values())
    log(f"{name}: {len(items)} listings, {sum(1 for c in items if c['fuel'] == 'rafmagn')} electric")
    return items


VAN_RE = re.compile(r"\bvan\b|sendib[ií]l|\bpartner\b|\bexpert\b|transit|\betp\s*3\b|crafter|transporter|"
                    r"proace|berlingo|\bkangoo\b|\bvito\b|evito|e[\s-]?nv200|\bcargo\b|\bpallb[ií]l|\bjumpy\b|"
                    r"\bboxer\b|\bmaster\b|\btrafic\b|\bdeliver\b|\bcombo\b", re.I)


def is_van(title):
    return bool(VAN_RE.search(title or ""))
