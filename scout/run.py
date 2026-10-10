"""Car scout — one run: collect listings → keep BEVs → fit market depreciation →
cost per km with the best selling year for each car → results.md, data/, notification."""
from __future__ import annotations

import csv
import datetime as dt
import json
import os
import sys
import traceback
from pathlib import Path

import requests
import yaml

from . import cost, models, sources
from .market import Market, car_age

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
LOG = []


def log(msg):
    print(msg, flush=True)
    LOG.append(msg)


def fmt(n):
    return f"{round(n):,}".replace(",", ".")


def main():
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text())
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    DATA.mkdir(exist_ok=True)
    state_path = DATA / "listings.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else {}

    health, raw = {}, []
    b = cfg["sources"]["bland"]
    try:
        got = sources.bland(b["category"], b["max_pages"], log, debug_dir=DATA / "debug")
        raw += got
        health["Bland"] = len(got)
    except Exception as e:
        log(f"Bland: FAILED — {type(e).__name__}: {e}")
        health["Bland"] = f"failed: {type(e).__name__}"

    f = cfg["filters"]
    cars = []
    for c in raw:
        if not sources.is_electric(c.get("fuel"), c.get("title")):
            continue
        if not c.get("year") or c.get("km") is None or not c.get("price"):
            continue
        if not (f["min_price_isk"] <= c["price"] <= f["max_price_isk"]):
            continue
        c["model"], c["make"], c["kwh_100km"] = models.identify(c["title"])
        cars.append(c)
    log(f"{len(cars)} electric cars with year, km and price")

    market = Market(cars, ridge=cfg["market"]["ridge"], min_listings=cfg["market"]["min_listings_per_model"])
    D = cfg["usage"]["km_per_year"]
    log(f"Market fit on {market.n} listings: value falls {market.yearly_depreciation(D):.1%}/yr at {fmt(D)} km/yr "
        f"(age {-market.a:.3f}/yr, km {-market.b:.3f}/10k km in log price), residual σ {market.sigma:.2f}")

    rows = []
    for c in cars:
        r = cost.evaluate(c, market, cfg)
        if r is None:
            continue
        prev = state.get(c["url"], {})
        rec = {**c, **r, "first_seen": prev.get("first_seen", now), "last_seen": now}
        if prev.get("price") and prev["price"] != c["price"]:
            rec["prev_price"] = prev["price"]
        rows.append(rec)
    new_urls = {r["url"] for r in rows if r["url"] not in state}
    for r in rows:
        state[r["url"]] = {k: r.get(k) for k in ("title", "price", "year", "km", "model", "first_seen", "last_seen", "prev_price")}
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=1))

    rows.sort(key=lambda r: r["kr_per_km"])
    # Rank only recent model years; older listings were used above for the market fit only
    rows = [r for r in rows if r["year"] >= f.get("min_year", 0)]
    log(f"{len(rows)} cars from {f.get('min_year')} on ranked")
    write_csv(rows)
    write_md(rows, market, cfg, health, now, new_urls)
    notify(rows[:10], new_urls)
    (DATA / "last_run.log").write_text("\n".join(LOG) + "\n", encoding="utf-8")


def write_csv(rows):
    cols = ["kr_per_km", "hold_years", "title", "model", "year", "km", "price", "market_value", "deal", "resale",
            "url", "first_seen"]
    with open(DATA / "results.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols + ["breakdown", "flags"], extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({**{k: r.get(k) for k in cols},
                        "breakdown": json.dumps({k: round(v, 1) for k, v in r["breakdown"].items()}),
                        "flags": "; ".join(r["flags"])})


LABELS = [("depreciation", "depreciation"), ("opportunity", "capital 7%"), ("energy", "charging"),
          ("km_fee", "km-gjald"), ("insurance", "insurance"), ("maintenance", "service"),
          ("tyres", "tyres"), ("tax", "tax/skoðun"), ("battery", "battery risk")]


def card(r, new, rate):
    bd = r["breakdown"]
    parts = " · ".join(f"{lab.replace('7%', f'{rate:.0%}')} {bd[k]:.1f}" for k, lab in LABELS if bd.get(k, 0) >= 0.05)
    deal = r["deal"]
    deal_txt = (f"{-deal:.0%} under market" if deal < -0.03 else f"{deal:.0%} over market" if deal > 0.03 else "at market")
    price = f"{fmt(r['price'])} kr"
    if r.get("prev_price") and r["prev_price"] > r["price"]:
        price += f" (was {fmt(r['prev_price'])})"
    out = [f"**{r['kr_per_km']:.1f} kr/km** · sell after **{r['hold_years']} yr** · {price}" + (" · 🆕" if new else ""), ""]
    if r.get("image"):
        out += [f'<a href="{r["url"]}"><img src="{r["image"]}" width="320"></a>', ""]
    out += [f"[{r['title']}]({r['url']})  ",
            f"<sub>{r['year']} · {fmt(r['km'])} km · {r['source']} · {r['model']} · {deal_txt} "
            f"(market ≈ {fmt(r['market_value'])} kr, resale ≈ {fmt(r['resale'])} kr)</sub>", "",
            f"<sub>kr/km: {parts}</sub>"]
    if r["flags"]:
        out += ["", f"<sub>⚠️ {'; '.join(r['flags'])}</sub>"]
    return "\n".join(out + ["", "---", ""])


def write_md(rows, market, cfg, health, now, new):
    D = cfg["usage"]["km_per_year"]
    rate = cfg["money"]["opportunity_rate"]
    lines = ["# Cheapest EVs per km", "",
             f"Updated {now} · {len(rows)} battery-electric cars from {cfg['filters'].get('min_year')} on · {fmt(D)} km/yr · capital at {rate:.0%} · "
             f"best selling year chosen per car (max {cfg['usage']['max_hold_years']} yr)", "",
             f"Market: EVs lose about **{market.yearly_depreciation(D):.0%} of their value per year** at this mileage "
             f"(fitted on all {market.n} EV listings, older ones included). Costs in today's krónur. Assumptions: `config.yaml`.", "",
             "<details><summary>How the number is built</summary>", "",
             "cost per km = (price − resale after N years + capital cost + charging + kílómetragjald + insurance + "
             "service + tyres + tax/skoðun + expected battery repairs after warranty) ÷ km driven. "
             "Resale comes from today's market: what the same model sells for N years older and "
             f"{fmt(D)}·N km further on. N is whichever year gives the lowest cost per km.", "",
             "</details>", "", "---", ""]
    lines += [card(r, r["url"] in new, rate) for r in rows[:60]]
    lines += ["<details><summary>Source status</summary>", ""]
    lines += [f"- {k}: {v}" for k, v in health.items()]
    lines += ["", "</details>", ""]
    (ROOT / "results.md").write_text("\n".join(lines), encoding="utf-8")


def notify(top, new):
    hits = [r for r in top if r["url"] in new]
    token, repo = os.environ.get("GITHUB_TOKEN"), os.environ.get("GITHUB_REPOSITORY")
    if not hits or not token or not repo:
        log(f"Notify: {len(hits)} new cars in the top 10")
        return
    h = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    api = f"https://api.github.com/repos/{repo}"
    title = "🚗 New cheap-per-km EVs"
    issues = requests.get(f"{api}/issues", headers=h, params={"state": "open", "per_page": 50}).json()
    num = next((i["number"] for i in issues if i.get("title") == title), None)
    if num is None:
        num = requests.post(f"{api}/issues", headers=h, json={
            "title": title, "body": "New listings entering the top 10 are posted here.",
            "assignees": [repo.split("/")[0]]}).json()["number"]
    body = "\n".join(f"- **{r['kr_per_km']:.1f} kr/km** (sell after {r['hold_years']} yr) [{r['title']}]({r['url']}) — "
                     f"{fmt(r['price'])} kr · {r['year']} · {fmt(r['km'])} km" for r in hits)
    requests.post(f"{api}/issues/{num}/comments", headers=h, json={"body": body})
    log(f"Notify: posted {len(hits)} cars to issue #{num}")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        (DATA / "last_run.log").write_text("\n".join(LOG) + "\n" + traceback.format_exc(), encoding="utf-8")
        sys.exit(1)
