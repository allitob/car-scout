"""Price model fitted on today's listings.

log(price) = level(model) + a·age + b·(km / 10.000)

Model levels are shrunk toward their make, and makes toward the overall level (ridge), so a model
with 2 listings borrows from its brand instead of producing nonsense. The age and km slopes are
shared: that's the depreciation the market shows across all EVs right now, in today's krónur.
"""
from __future__ import annotations

import datetime as dt
import math

import numpy as np


def car_age(year, today=None):
    today = today or dt.date.today()
    # A model year is on the road from about mid-year on average
    return max(0.0, today.year + (today.timetuple().tm_yday / 365.0) - (year + 0.5))


class Market:
    def __init__(self, cars, ridge=2.0, min_listings=3):
        rows = [c for c in cars if c.get("price") and c.get("year") and c.get("km") is not None]
        self.n = len(rows)
        if self.n < 15:
            raise ValueError(f"only {self.n} usable EV listings — too few to fit depreciation")
        models = sorted({c["model"] for c in rows})
        makes = sorted({c["make"] for c in rows})
        mi = {m: i for i, m in enumerate(models)}
        ki = {m: i for i, m in enumerate(makes)}
        p = 3 + len(makes) + len(models)
        X = np.zeros((self.n, p))
        y = np.zeros(self.n)
        for r, c in enumerate(rows):
            X[r, 0] = 1
            X[r, 1] = car_age(c["year"])
            X[r, 2] = c["km"] / 1e4
            X[r, 3 + ki[c["make"]]] = 1
            X[r, 3 + len(makes) + mi[c["model"]]] = 1
            y[r] = math.log(c["price"])
        pen = np.zeros(p)
        pen[3:] = ridge
        beta = np.linalg.solve(X.T @ X + np.diag(pen), X.T @ y)
        self.beta, self.makes, self.models, self.ki, self.mi = beta, makes, models, ki, mi
        self.a, self.b = float(beta[1]), float(beta[2])
        resid = y - X @ beta
        self.sigma = float(np.sqrt(np.mean(resid ** 2)))
        self.max_age = float(X[:, 1].max())
        self.max_km = float(X[:, 2].max() * 1e4)
        # How well each model is covered by the data
        self.coverage = {}
        for m in models:
            ms = [c for c in rows if c["model"] == m]
            self.coverage[m] = {"n": len(ms), "years": len({c["year"] for c in ms}),
                                "oldest_age": max(car_age(c["year"]) for c in ms)}
        self.min_listings = min_listings

    def level(self, model, make):
        v = self.beta[0]
        if make in self.ki:
            v += self.beta[3 + self.ki[make]]
        if model in self.mi:
            v += self.beta[3 + len(self.makes) + self.mi[model]]
        return v

    def value(self, model, make, age, km):
        """Typical market value (median) of this model at this age and mileage."""
        return math.exp(self.level(model, make) + self.a * age + self.b * km / 1e4)

    def measured(self, model):
        """True when this model's own listings span enough years to trust its depreciation."""
        c = self.coverage.get(model)
        return bool(c and c["n"] >= self.min_listings and c["years"] >= 3)

    def yearly_depreciation(self, km_per_year):
        """Share of value lost per year at this usage, from the fitted slopes."""
        return 1 - math.exp(self.a + self.b * km_per_year / 1e4)
