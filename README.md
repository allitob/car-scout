# car-scout

Ranks used battery-electric cars for sale in Iceland by **total cost per km**, and for each car
picks the year it's cheapest to sell it.

**Latest results → [results.md](results.md)**

## How it works

1. Collects car listings daily (GitHub Actions, 07:37 UTC) from Bland.is and keeps the fully electric ones.
2. Fits today's market: log(price) against age and mileage, with a price level per model (shrunk toward its
   brand when a model has few listings). That gives what any car is worth N years older and N·20.000 km further on.
3. For each car and each holding period (1–12 years): price − resale + capital cost (7%) + charging +
   kílómetragjald + insurance + service + tyres + tax/skoðun + expected battery repairs after warranty,
   divided by km driven. The cheapest year wins.
4. Writes `results.md` and `data/results.csv`; new listings entering the top 10 are posted to the
   "🚗 New cheap-per-km EVs" issue (phone notification).

Brands with no used history in Iceland (Leapmotor, BYD, Xpeng…) and models with too few listings get their
depreciation and battery risk scaled up by `battery.uncertainty_factor`, and are flagged.

## Adjusting

Everything is in `config.yaml`. Lines marked **CHECK** are estimates (electricity price, insurance, tax) —
replace them with real numbers. Consumption per model is in `scout/models.py`.
