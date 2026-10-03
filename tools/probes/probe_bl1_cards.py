# Dev probe (in game), instant, read-only: Borderlands 1's weapon card lines (.agent/bl1.md) - the page showed an SG330's
# "20x weapon zoom, +0.5 fire rate, +8 projectiles fired" where the game says "4.0x, +43% fire rate, +1 projectiles
# fired": BL2's lines show their attribute's current value ("cur": the shot cost's 2), BL1's every line has one. The raw
# entries, to show them as the game does:
# every weapon of the player's (held, backpack) and the vending machines': its name, its WeaponCardModifierStats
# entries {ModifierValue, bShouldDisplay, ...} with their presentation's text, flags (percentage, inverse, sign, rounding),
# its Attribute and that attribute's current value on the weapon (what the page showed).
# Properties only (the attribute's value: the mod's own reader, inspector._attribute_value). Writes
# tools/probes/probe_bl1_cards.txt (appends).
#   py exec(open(r"<repo>\tools\probes\probe_bl1_cards.py").read())
from enum import Enum
import sys
from pathlib import Path

import unrealsdk


def _out() -> Path:
    if (mod := sys.modules.get("helios_tracker")) is not None and getattr(mod, "__file__", None):
        return Path(mod.__file__).resolve().parents[1] / "tools" / "probes" / "probe_bl1_cards.txt"
    for entry in sys.path:
        if (link := Path(entry) / "helios_tracker").is_dir():
            return link.resolve().parent / "tools" / "probes" / "probe_bl1_cards.txt"
    raise RuntimeError("helios_tracker isn't linked in sdk_mods (python tools/link_mod.py bl1)")


OUT = _out()
lines: list[str] = ["#" * 70]


def _flush() -> None:
    with OUT.open("a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    lines.clear()


def _try(fn, default="<err>"):  # noqa: ANN001, ANN202
    try:
        return fn()
    except Exception as ex:  # noqa: BLE001
        return f"<{type(ex).__name__}: {ex}>"[:160] if default == "<err>" else default


def _brief(value) -> str:  # noqa: ANN001
    if value is None:
        return "None"
    if isinstance(value, Enum):
        return str(value.name)
    if isinstance(value, float):
        return f"{value:.4f}"
    if isinstance(value, (str, int, bool)):
        return repr(value) if isinstance(value, str) else str(value)
    if hasattr(value, "_path_name") and hasattr(value, "Class"):
        return f"{_try(lambda: value.Class.Name)}'{_try(lambda: value._path_name())}'"
    return "<struct>"


inspector = sys.modules.get("helios_tracker.inspector")
util = sys.modules.get("helios_tracker.util")
pawn = _try(lambda: __import__("mods_base").get_pc().Pawn, None)
machines = [m for m in _try(lambda: list(unrealsdk.find_all("WillowVendingMachine", exact=False)), []) or []
            if not str(m.Name).startswith("Default__")]
weapons = [w for w in _try(lambda: list(unrealsdk.find_all("WillowWeapon", exact=False)), []) or []
           if not str(w.Name).startswith("Default__") and _try(lambda w=w: w.Owner == pawn or w.Owner in machines, False)]
lines.append(f"== {len(weapons)} weapons (the player's, the machines')")
for w in weapons[:20]:
    name = _try(lambda w=w: util.item_name(w)) if util is not None else "-"
    entries = _try(lambda w=w: list(w.WeaponCardModifierStats), [])
    lines.append(f"-- {w._path_name()} {name!r} (owner {_brief(_try(lambda w=w: w.Owner))}): {len(entries) if isinstance(entries, list) else entries} lines")
    for e in entries if isinstance(entries, list) else []:
        p = _try(lambda e=e: e.AttributePresentation, None)
        attribute = _try(lambda p=p: p.Attribute, None) if p is not None else None
        current = _try(lambda a=attribute, w=w: inspector._attribute_value(w, a)) if inspector is not None and attribute is not None else "-"
        entry_fields = ", ".join(f"{f.Name}={_brief(_try(lambda f=f, e=e: e._get_field(f)))}"
                                 for f in (_try(lambda e=e: list(e._type._fields()), []) or []) if f.Class.Name.endswith("Property")
                                 and str(f.Name) != "AttributePresentation")
        pres = ", ".join(f"{n}={_brief(_try(lambda n=n, p=p: getattr(p, n)))}" for n in (
            "Description", "NoConstraintText", "Suffix", "bDisplayAsPercentage", "bDisplayAsInverse", "bDontDisplayPlusSign",
            "bDontDisplayNumber", "SignStyle", "RoundingMode", "bValueRemappingEnabled", "bBiggerIsBetter")) if p is not None else "-"
        lines.append(f"   {entry_fields}")
        lines.append(f"     presentation {_brief(p)}: {pres}")
        lines.append(f"     attribute {_brief(attribute)}, its current value on the weapon {_brief(current)}")
    _flush()
lines.append("== done")
_flush()
print(f"probe_bl1_cards: written to {OUT}")
