"""Total cost of owning one listed car, and the cheapest year to sell it.

For each holding period h = 1..max years:
  cost(h) = asking price − resale after h years (minus selling spread)
          + Σ yearly: opportunity cost on the money tied up, energy, kílómetragjald,
            insurance, tax+inspection, tyres, maintenance, expected battery repairs
  cost per km(h) = cost(h) / (km_per_year · h)
The car's result is the h with the lowest cost per km.
"""
from __future__ import annotations

import math

from .market import car_age


def evaluate(car, market, cfg):
    u, m, e, run, bat = cfg["usage"], cfg["money"], cfg["energy"], cfg["running"], cfg["battery"]
    D = u["km_per_year"]
    age0 = car.get("age", car_age(car["year"]))
    km0 = car["km"]
    price = car["price"]

    young = car["make"] in bat["young_brands"]
    measured = market.measured(car["model"])
    unc = bat["uncertainty_factor"] if (young or not measured) else 1.0
    # Depreciation per year from the shared slopes; scaled up when the model's own history is missing
    step = math.exp(unc * (market.a + market.b * D / 1e4))
    v_market = market.value(car["model"], car["make"], age0, km0)
    # A price below/above the market usually reflects condition, spec or battery health, so most of
    # the gap stays with the car when it's resold (price_gap_persists = 1: all of it)
    # New cars: the gap between list price and a nearly-new used one is the showroom premium — it's gone at resale
    if car.get("new"):
        # Value right after registration: the used market's level for this model, but never above what
        # was paid minus the registration drop (thin data can put a model's used level above its new price)
        v_now = min(v_market, price * (1 - cfg["new_cars"].get("registration_drop", 0.10)))
    else:
        keep = m.get("price_gap_persists", 0.8)
        v_now = v_market * (price / v_market) ** keep

    energy_kr_per_km = (car["kwh_100km"] / 100 * e["winter_factor"] * (1 + e["charging_loss"])
                        * (e["home_share"] * e["home_kr_per_kwh"] + (1 - e["home_share"]) * e["public_kr_per_kwh"]))

    best = None
    totals = {"depreciation": 0, "opportunity": 0, "energy": 0, "km_fee": 0, "insurance": 0,
              "tax": 0, "tyres": 0, "maintenance": 0, "battery": 0}
    prev_v = price
    capped = False
    for h in range(1, u["max_hold_years"] + 1):
        age_end, km_end = age0 + h, km0 + D * h
        # Don't extrapolate far beyond the oldest / highest-mileage cars actually on the market
        if age_end > market.max_age + 2 or km_end > market.max_km + 2 * D:
            capped = True
            break
        v = v_now * step ** h
        mid_v = (prev_v + v) / 2
        mid_age, mid_km = age0 + h - 0.5, km0 + D * (h - 0.5)
        totals["opportunity"] += m["opportunity_rate"] * mid_v
        totals["energy"] += energy_kr_per_km * D
        totals["km_fee"] += run["km_fee_kr"] * D
        totals["insurance"] += run["insurance_fixed_kr"] + run["insurance_kasko_share"] * mid_v
        totals["tax"] += run["tax_and_inspection_kr"]
        totals["tyres"] += run["tyres_kr_per_km"] * D
        totals["maintenance"] += (run["maintenance_base_kr"]
                                  + run["maintenance_growth_kr_per_year"] * max(0.0, mid_age - run["maintenance_warranty_years"]))
        over = max(mid_age - bat["warranty_years"], (mid_km - bat["warranty_km"]) / D)
        if over > 0:
            p = (bat["failure_rate_per_year"] + bat["failure_rate_growth_per_year"] * over) * (bat["uncertainty_factor"] if young else 1.0)
            totals["battery"] += min(p, 1.0) * bat["repair_cost_kr"]
        prev_v = v

        resale = v * (1 - m["sell_spread"])
        dep = price - resale
        total = dep + sum(val for k, val in totals.items() if k != "depreciation")
        per_km = total / (D * h)
        if best is None or per_km < best["kr_per_km"]:
            parts = dict(totals, depreciation=dep)
            best = {"hold_years": h, "kr_per_km": per_km, "resale": resale,
                    "breakdown": {k: val / (D * h) for k, val in parts.items()}}

    if best is None:
        return None
    flags = []
    if capped and best["hold_years"] == h - 1:
        km_at = round((km0 + D * best["hold_years"]) / 1000)
        flags.append(f"still getting cheaper per km at {best['hold_years']} yr / {km_at}.000 km, where market data ends — "
                     "keeping it longer is probably cheaper still")
    if young:
        flags.append("young brand in Iceland: depreciation & battery guessed")
    elif not measured:
        flags.append("little market data for this model: depreciation borrowed from brand/all EVs")
    if car["model"] == "unknown" or car["model"].endswith("(other)"):
        flags.append("model not recognised: consumption assumed")
    deal = price / v_market - 1
    best.update({"market_value": v_market, "deal": deal, "energy_kr_per_km": energy_kr_per_km,
                 "flags": flags, "uncertainty": unc})
    return best
