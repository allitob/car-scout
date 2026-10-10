"""Known EV models: how to recognise them in a listing title, and typical consumption.

kwh_100km = typical real-world consumption in a mild climate (battery side, kWh/100 km).
These are rough estimates — config.energy.winter_factor and charging_loss adjust for Iceland.
Order matters: more specific patterns first.
"""
from __future__ import annotations

import re
import unicodedata

# (key, make, regex on the ascii-folded lowercase title, kwh_100km)
MODELS = [
    ("tesla model 3", "tesla", r"model\s*3|\bm3\b", 15.5),
    ("tesla model y", "tesla", r"model\s*y\b", 17.0),
    ("tesla model s", "tesla", r"model\s*s\b", 19.5),
    ("tesla model x", "tesla", r"model\s*x\b", 22.5),
    ("nissan ariya", "nissan", r"ariya", 19.5),
    ("nissan leaf", "nissan", r"\bleaf\b|\blauf\b", 17.0),
    ("vw e-golf", "volkswagen", r"e[\s-]?golf", 16.0),
    ("vw e-up", "volkswagen", r"e[\s-]?up\b", 14.0),
    ("vw id.3", "volkswagen", r"\bid\.?\s*3\b", 16.5),
    ("vw id.4", "volkswagen", r"\bid\.?\s*4\b", 19.0),
    ("vw id.5", "volkswagen", r"\bid\.?\s*5\b", 19.0),
    ("vw id.7", "volkswagen", r"\bid\.?\s*7\b", 17.0),
    ("vw id.buzz", "volkswagen", r"\bid\.?\s*buzz", 22.0),
    ("skoda enyaq", "skoda", r"enyaq", 18.5),
    ("skoda elroq", "skoda", r"elroq", 17.0),
    ("cupra born", "cupra", r"\bborn\b", 16.5),
    ("audi q4 e-tron", "audi", r"q4", 19.0),
    ("audi e-tron gt", "audi", r"e[\s-]?tron\s*gt", 21.0),
    ("audi e-tron", "audi", r"e[\s-]?tron|q8", 24.0),
    ("kia ev3", "kia", r"\bev\s*3\b", 16.5),
    ("kia ev6", "kia", r"\bev\s*6\b", 18.5),
    ("kia ev9", "kia", r"\bev\s*9\b", 23.0),
    ("kia niro ev", "kia", r"e[\s-]?niro|niro\s*(ev|electric|rafmagn)", 16.0),
    ("kia soul ev", "kia", r"soul", 16.0),
    ("hyundai ioniq 5", "hyundai", r"ioniq\s*5", 19.0),
    ("hyundai ioniq 6", "hyundai", r"ioniq\s*6", 16.0),
    ("hyundai ioniq electric", "hyundai", r"ioniq", 13.5),
    ("hyundai kona electric", "hyundai", r"kona", 15.5),
    ("polestar 2", "polestar", r"polestar\s*2", 18.5),
    ("polestar 3/4", "polestar", r"polestar\s*[34]", 21.0),
    ("volvo ex30", "volvo", r"ex\s*30", 17.0),
    ("volvo c40", "volvo", r"c\s*40|ec\s*40", 20.0),
    ("volvo xc40 recharge", "volvo", r"xc\s*40|ex\s*40", 21.0),
    ("volvo ex90", "volvo", r"ex\s*90", 23.0),
    ("mg4", "mg", r"\bmg\s*4\b", 17.0),
    ("mg5", "mg", r"\bmg\s*5\b", 17.0),
    ("mg zs ev", "mg", r"\bzs\b", 18.0),
    ("mg marvel r", "mg", r"marvel", 20.0),
    ("byd dolphin", "byd", r"dolphin", 15.5),
    ("byd atto 3", "byd", r"atto\s*3", 17.5),
    ("byd seal", "byd", r"\bseal\b|sealion", 17.5),
    ("byd tang", "byd", r"\btang\b", 22.0),
    ("mercedes eqa", "mercedes", r"\beqa\b", 18.0),
    ("mercedes eqb", "mercedes", r"\beqb\b", 19.0),
    ("mercedes eqc", "mercedes", r"\beqc\b", 24.0),
    ("mercedes eqe", "mercedes", r"\beqe\b", 19.0),
    ("mercedes eqs", "mercedes", r"\beqs\b", 20.0),
    ("mercedes eqv", "mercedes", r"\beqv\b", 26.0),
    ("bmw i3", "bmw", r"\bi3\b", 15.0),
    ("bmw i4", "bmw", r"\bi4\b", 17.0),
    ("bmw ix1", "bmw", r"\bix1\b", 18.0),
    ("bmw ix3", "bmw", r"\bix3\b", 19.0),
    ("bmw ix", "bmw", r"\bix\b", 21.0),
    ("renault zoe", "renault", r"\bzo[eé]\b", 16.5),
    ("renault megane e-tech", "renault", r"megane", 16.5),
    ("peugeot e-208", "peugeot", r"e[\s-]?208", 15.5),
    ("peugeot e-2008", "peugeot", r"e[\s-]?2008", 17.0),
    ("opel corsa-e", "opel", r"corsa", 15.5),
    ("opel mokka-e", "opel", r"mokka", 17.0),
    ("citroen e-c4", "citroen", r"e[\s-]?c4|\bc4\b", 17.0),
    ("toyota bz4x", "toyota", r"bz\s*4x", 18.5),
    ("subaru solterra", "subaru", r"solterra", 18.5),
    ("ford mustang mach-e", "ford", r"mach[\s-]?e|mustang", 20.0),
    ("jaguar i-pace", "jaguar", r"i[\s-]?pace", 24.0),
    ("porsche taycan", "porsche", r"taycan", 22.0),
    ("mazda mx-30", "mazda", r"mx[\s-]?30", 18.0),
    ("honda e", "honda", r"honda\s*e\b", 17.0),
    ("fiat 500e", "fiat", r"500\s*e\b|500\s*(electric|rafmagn)", 15.0),
    ("smart #1", "smart", r"smart\s*#?\s*1\b", 18.0),
    ("leapmotor t03", "leapmotor", r"t\s*03", 15.0),
    ("leapmotor c10", "leapmotor", r"c\s*10", 19.0),
    ("xpeng g6", "xpeng", r"\bg6\b", 18.0),
    ("lexus ux300e", "lexus", r"ux\s*300", 17.0),
    ("dacia spring", "dacia", r"spring", 14.0),
    ("maxus", "maxus", r"maxus|euniq|mifa", 22.0),
]

MAKE_WORDS = {
    "tesla": "tesla", "nissan": "nissan", "volkswagen": "volkswagen", "vw": "volkswagen", "skoda": "skoda",
    "cupra": "cupra", "audi": "audi", "kia": "kia", "hyundai": "hyundai", "polestar": "polestar",
    "volvo": "volvo", "mg": "mg", "byd": "byd", "mercedes": "mercedes", "benz": "mercedes", "bmw": "bmw",
    "renault": "renault", "peugeot": "peugeot", "opel": "opel", "citroen": "citroen", "toyota": "toyota",
    "subaru": "subaru", "ford": "ford", "jaguar": "jaguar", "porsche": "porsche", "mazda": "mazda",
    "honda": "honda", "fiat": "fiat", "smart": "smart", "leapmotor": "leapmotor", "xpeng": "xpeng",
    "lexus": "lexus", "dacia": "dacia", "maxus": "maxus", "zeekr": "zeekr", "nio": "nio", "lynk": "lynk",
    "seat": "seat", "mini": "mini", "jeep": "jeep", "ora": "ora",
}

DEFAULT_KWH_100KM = 19.0


def fold(s: str) -> str:
    s = (s or "").lower().replace("ð", "d").replace("þ", "th").replace("æ", "ae").replace("ö", "o")
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()


def identify(title: str):
    """Return (model_key, make, kwh_100km). Unknown models keep their make if one is named."""
    t = fold(title)
    make = next((m for w, m in MAKE_WORDS.items() if re.search(rf"\b{re.escape(w)}\b", t)), None)
    for key, mk, rx, kwh in MODELS:
        if re.search(rx, t) and (make is None or make == mk or (mk == "volkswagen" and make == "volkswagen")):
            return key, mk, kwh
    return (f"{make} (other)" if make else "unknown"), (make or "unknown"), DEFAULT_KWH_100KM
