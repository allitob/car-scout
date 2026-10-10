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
    ("tesla model 3", "tesla", r"model\s*3|tesla\s*3\b|\bm3\b", 15.5),
    ("tesla model y", "tesla", r"model\s*y\b|tesla\s*y\b", 17.0),
    ("tesla model s", "tesla", r"model\s*s\b|tesla\s*s\b", 19.5),
    ("tesla model x", "tesla", r"model\s*x\b|tesla\s*x\b", 22.5),
    ("nissan ariya", "nissan", r"ariya", 19.5),
    ("nissan leaf", "nissan", r"\bleaf\b|\blauf\b", 17.0),
    ("vw e-golf", "volkswagen", r"e[\s-]?golf|golf", 16.0),
    ("vw e-up", "volkswagen", r"\bup\b", 14.0),
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
    ("audi q6 e-tron", "audi", r"q6", 20.0),
    ("audi e-tron", "audi", r"e[\s-]?tron|q8", 24.0),
    ("kia ev3", "kia", r"\bev\s*3\b", 16.5),
    ("kia ev5", "kia", r"\bev\s*5\b", 19.0),
    ("kia ev6", "kia", r"\bev\s*6\b", 18.5),
    ("kia ev9", "kia", r"\bev\s*9\b", 23.0),
    ("kia niro ev", "kia", r"niro", 16.0),
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
    ("mercedes eqa", "mercedes", r"\beqa\s*\d*\b", 18.0),
    ("mercedes eqb", "mercedes", r"\beqb\s*\d*\b", 19.0),
    ("mercedes eqc", "mercedes", r"\beqc\s*\d*\b", 24.0),
    ("mercedes eqe", "mercedes", r"\beqe\s*\d*\b", 19.0),
    ("mercedes eqs", "mercedes", r"\beqs\s*\d*\b", 20.0),
    ("mercedes eqv", "mercedes", r"\beqv\b", 26.0),
    ("bmw i3", "bmw", r"\bi3\b", 15.0),
    ("bmw i4", "bmw", r"\bi4\b", 17.0),
    ("bmw i5", "bmw", r"\bi5\b", 19.0),
    ("bmw i7", "bmw", r"\bi7\b", 22.0),
    ("bmw ix1", "bmw", r"\bix1\b", 18.0),
    ("bmw ix3", "bmw", r"\bix3\b", 19.0),
    ("bmw ix", "bmw", r"\bix\b", 21.0),
    ("renault zoe", "renault", r"\bzo[eé]\b", 16.5),
    ("renault megane e-tech", "renault", r"megane", 16.5),
    ("peugeot e-208", "peugeot", r"\b(e[\s-]?)?208\b", 15.5),
    ("peugeot e-2008", "peugeot", r"2008", 17.0),
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
    ("fiat 500e", "fiat", r"500\s*e\b|e\s*500|\b500\b", 15.0),
    ("smart #1", "smart", r"smart\s*#?\s*1\b", 18.0),
    ("leapmotor t03", "leapmotor", r"t\s*03", 15.0),
    ("leapmotor c10", "leapmotor", r"c\s*10", 19.0),
    ("xpeng g6", "xpeng", r"\bg6\b", 18.0),
    ("lexus ux300e", "lexus", r"ux\s*300", 17.0),
    ("dacia spring", "dacia", r"spring", 14.0),
    ("nissan e-nv200", "nissan", r"nv\s*200", 20.0),
    ("mercedes b 250e", "mercedes", r"\bb\s*(250\s*e|klass|class)?\b", 17.0),
    ("vw e-crafter", "volkswagen", r"crafter", 28.0),
    ("vw transporter abt-e", "volkswagen", r"transporter|abt", 25.0),
    ("ford explorer ev", "ford", r"explorer", 18.0),
    ("cadillac lyriq", "cadillac", r"lyriq", 22.0),
    ("hongqi e-hs9", "hongqi", r"e[\s-]?hs\s*9", 26.0),
    ("byd etp3", "byd", r"etp\s*3", 22.0),
    ("ford puma ev", "ford", r"puma", 15.5),
    ("skoda epiq", "skoda", r"epiq", 15.0),
    ("skoda peaq", "skoda", r"peaq", 21.0),
    ("vw id.polo", "volkswagen", r"\bid\.?\s*polo", 15.0),
    ("vw id.cross", "volkswagen", r"\bid\.?\s*cross", 16.5),
    ("peugeot e-3008", "peugeot", r"3008", 18.5),
    ("peugeot e-5008", "peugeot", r"5008", 19.5),
    ("volvo ex60", "volvo", r"ex\s*60", 19.0),
    ("mazda cx-6e", "mazda", r"cx[\s-]?6e", 18.5),
    ("audi q6 e-tron", "audi", r"q6", 20.0),
    ("renault 5", "renault", r"\br5\b|renault\s*5\b", 15.0),
    ("renault 4", "renault", r"\br4\b|renault\s*4\b", 16.0),
    ("hyundai inster", "hyundai", r"inster", 14.5),
    ("citroen e-c3", "citroen", r"e[\s-]?c3", 16.0),
    ("maxus", "maxus", r"maxus|euniq|mifa", 22.0),
]

MAKE_WORDS = {
    "tesla": "tesla", "nissan": "nissan", "volkswagen": "volkswagen", "vw": "volkswagen", "skoda": "skoda",
    "cupra": "cupra", "audi": "audi", "kia": "kia", "hyundai": "hyundai", "polestar": "polestar",
    "volvo": "volvo", "mg": "mg", "nizzan": "nissan", "cadillac": "cadillac", "hongqi": "hongqi", "byd": "byd", "mercedes": "mercedes", "benz": "mercedes", "bmw": "bmw",
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
    # The make named first in the title wins ("Nizzan E-NV200 Skoða skipti" is a Nissan)
    hits = [(mt.start(), m) for w, m in MAKE_WORDS.items() for mt in [re.search(rf"\b{re.escape(w)}\b", t)] if mt]
    make = min(hits)[1] if hits else None
    for key, mk, rx, kwh in MODELS:
        if re.search(rx, t) and (make is None or make == mk or (mk == "volkswagen" and make == "volkswagen")):
            return key, mk, kwh
    return (f"{make} (other)" if make else "unknown"), (make or "unknown"), DEFAULT_KWH_100KM
