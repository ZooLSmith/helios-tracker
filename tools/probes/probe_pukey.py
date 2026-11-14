# Dev probe (in game), instant, read-only: a friendly pawn the page draws as an enemy - Ol' Pukey (Sir Hammerlock's
# Big Game Hunt, Scylla's Grove, the mission "Ol' Pukey": "Protect Pukey"), pawn.IsEnemy(player pawn) True
# (2026-11-14, the user). What the game says about it, against an enemy (a Savage Hunter / any other) and the player:
# 1. each one's Allegiance (its definition's fields), AIClass, the controller and its fields with "Allegiance",
#    "Enemy", "Friend", "Target", "Hostile", "Neutral", "Faction" in their name - read, nothing called;
# 2. the pawns' functions with those words in their name: signatures only, not called;
# 3. IsEnemy(player pawn) (the collector's call, on the same pawns: nothing else is called).
# The pawns as the collector walks them (WorldInfo.PawnList: not deleted, dead or hidden) - its first version called
# IsEnemy on every WillowAIPawn find_all gave (templates, pawns out of play too) and crashed the game (2026-11-14):
# IsEnemy now on Pukey and one Savage only, both live pawns the collector calls it on already.
# Run near Pukey. Writes tools/probes/probe_pukey.txt (overwrites; section by section)
#   py exec(open(r"<repo>\tools\probes\probe_pukey.py").read())
import enum
import sys
from pathlib import Path

import unrealsdk

OUT = Path(sys.modules["helios_tracker"].__file__).resolve().parents[1] / "tools" / "probes" / "probe_pukey.txt"  # the repo, through the mod's junction
TARGET = "pukey"  # in its display name (lowercase)
WORDS = ("allegiance", "enemy", "friend", "hostile", "neutral", "faction", "target", "team")
lines: list[str] = []


def _try(fn, default="<err>"):  # noqa: ANN001, ANN202
    try:
        return fn()
    except Exception as ex:  # noqa: BLE001
        return f"<{type(ex).__name__}: {ex}>" if default == "<err>" else default


def _brief(value) -> str:  # noqa: ANN001
    if value is None:
        return "None"
    if isinstance(value, enum.Enum):
        return value.name
    if isinstance(value, float):
        return f"{value:.3f}"
    if hasattr(value, "_path_name") and hasattr(value, "Class"):
        return f"{value.Class.Name}:{value._path_name()}"
    return repr(value)[:300]


def _flush() -> None:
    with OUT.open("a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    lines.clear()


def _fields(obj, words=None, functions=False) -> dict[str, str]:  # noqa: ANN001
    """obj's properties (or functions: their signatures) whose name holds one of `words` (None: all), read."""
    out: dict[str, str] = {}
    c = _try(lambda: obj.Class, None)
    while c is not None and not isinstance(c, str) and str(c.Name) != "Object":
        for f in _try(lambda c=c: list(c._fields()), []) or []:
            name, kind = str(f.Name), str(f.Class.Name)
            if name in out or (kind == "Function") != functions or kind in ("Const", "Enum", "ScriptStruct"):
                continue
            if words is not None and not any(w in name.lower() for w in words):
                continue
            if functions:
                params = [f"{p.Class.Name.removesuffix('Property')} {p.Name}" for p in _try(lambda f=f: list(f._fields()), []) or []]
                out[name] = f"{c.Name}.{name}({', '.join(params)})"
            else:
                out[name] = f"{kind} = " + _try(lambda f=f: _brief(obj._get_field(f)))
        c = _try(lambda c=c: c.SuperField, None)
    return out


def _display(pawn) -> str:  # noqa: ANN001
    from helios_tracker.collector import pawn_display_name  # noqa: PLC0415

    return str(_try(lambda: pawn_display_name(pawn), ""))


OUT.write_text("", encoding="utf-8")
from mods_base import ENGINE, get_pc  # noqa: E402

me_pc = get_pc()
me = me_pc.MyWillowPawn if me_pc is not None else None  # (the player, not the vehicle driven: the collector's)
pawns, pawn = [], ENGINE.GetCurrentWorldInfo().PawnList
for _ in range(1000):
    if pawn is None:
        break
    if pawn.Class.Name != "WillowPlayerPawn" and not pawn.bDeleteMe and not pawn.bIsDead and not pawn.bHidden:
        pawns.append(pawn)
    pawn = pawn.NextPawn
pukey = [p for p in pawns if TARGET in _display(p).lower()]
others = [p for p in pawns if "savage" in _display(p).lower()][:1]  # (an enemy: the Savages around Pukey, not asked)
lines.append(f"me: {_brief(me)}; AI pawns {len(pawns)}; {TARGET!r}: {[_display(p) for p in pukey]}; an enemy: {[_display(p) for p in others]}")
_flush()

lines.append("== 1. allegiances, controllers")
for label, pawn in [("PUKEY", p) for p in pukey] + [("ENEMY", p) for p in others] + [("ME", me)]:
    if pawn is None:
        continue
    lines.append(f"-- {label} {_display(pawn)!r} {_brief(pawn)}")
    lines.append(f"   AIClass: {_brief(_try(lambda: pawn.AIClass))}")
    allegiance = _try(lambda: pawn.Allegiance, None)
    lines.append(f"   Allegiance: {_brief(allegiance)}")
    if allegiance is not None and not isinstance(allegiance, str):
        lines += [f"      {k}: {v}" for k, v in sorted(_fields(allegiance).items())]
    lines += [f"   pawn.{k}: {v}" for k, v in sorted(_fields(pawn, WORDS).items())]
    ctrl = _try(lambda: pawn.Controller, None)
    lines.append(f"   Controller: {_brief(ctrl)}")
    if ctrl is not None and not isinstance(ctrl, str):
        lines += [f"   ctrl.{k}: {v}" for k, v in sorted(_fields(ctrl, WORDS).items())]
    _flush()

lines.append("== 2. functions (signatures, not called)")
if pukey:
    lines += [f"   {v}" for _, v in sorted(_fields(pukey[0], WORDS, functions=True).items())]
_flush()

lines.append("== 3. IsEnemy")
for pawn in pukey + others:
    lines.append(f"   {_display(pawn)!r}: IsEnemy(me) {_try(lambda: pawn.IsEnemy(me))}")
_flush()
