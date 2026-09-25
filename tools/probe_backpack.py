# Dev probe (in game, as HOST with a friend in), read-only, then samples for 60 s: is another player's
# backpack really not on the host? Their InvManager.Backpack read empty (BackpackInventoryCount 0,
# a level 43 - probe_inventory.txt). Looks further:
#  1) every non-empty property of their inventory manager, and their controller's inventory-ish fields;
#  2) every inventory object in memory owned by them (Owner / Instigator = their pawn or manager), in a
#     list or not;
#  3) for 60 s: their backpack count / owned item count on every change - have them PICK UP an item
#     (the host runs pickups: it may land here) and then drop one.
# Writes tools/probe_backpack.txt (overwrites)
#   py exec(open(r"<repo>\tools\probe_backpack.py").read())
import re
import time
from enum import Enum
import sys
from pathlib import Path

import unrealsdk
from mods_base import ENGINE, get_pc
from unrealsdk.hooks import Type, add_hook, remove_hook

OUT = Path(sys.modules["helios_tracker"].__file__).resolve().parents[1] / "tools" / "probe_backpack.txt"  # the repo, through the mod's junction
SAMPLE_FOR, SAMPLE_EVERY = 60.0, 0.5
PC_KEYS = re.compile(r"Inv|Item|Backpack|Stash|Bank|Weapon|Gear|Equip|Save|Loadout", re.I)
INV_CLASSES = ("WillowWeapon", "WillowShield", "WillowGrenadeMod", "WillowClassMod", "WillowArtifact",
               "WillowUsableItem", "WillowUsableCustomizationItem", "WillowMissionItem")
lines: list[str] = []


def _try(fn, default="<err>"):  # noqa: ANN001, ANN202
    try:
        return fn()
    except Exception as ex:  # noqa: BLE001
        return f"<{type(ex).__name__}>" if default == "<err>" else default


def _brief(value, depth: int = 0) -> str:  # noqa: ANN001
    if value is None:
        return "None"
    if isinstance(value, Enum):
        return str(value.name)
    if isinstance(value, (str, int, float, bool)):
        return f"{value:.2f}" if isinstance(value, float) else str(value)
    if depth > 2:
        return "..."
    if hasattr(value, "_type"):
        return "{" + ", ".join(f"{f.Name}={_brief(_try(lambda f=f: value._get_field(f)), depth + 1)}"
                               for f in _try(lambda: list(value._type._fields()), [])
                               if f.Class.Name.endswith("Property")) + "}"
    if hasattr(value, "_path_name") and hasattr(value, "Class"):
        return f"{value.Class.Name}'{_try(lambda: value.Name)}'"
    if hasattr(value, "__len__"):
        return f"[{len(value)}: " + ", ".join(_brief(v, depth + 1) for v in list(value)[:8]) + "]"
    return str(value)


def _dump(title: str, obj, keep=None) -> None:  # noqa: ANN001
    lines.append(f"== {title}: {_brief(obj)}")
    if obj is None:
        return
    for f in _try(lambda: list(obj.Class._fields()), []):
        name = str(f.Name)
        if not f.Class.Name.endswith("Property") or (keep is not None and not keep.search(name)):
            continue
        text = _brief(_try(lambda f=f: obj._get_field(f)))
        if text in ("0", "0.00", "False", "None", "[0: ]", "{}", ""):
            continue
        lines.append(f"   {name:40s} {text[:300]}")


def _friend():  # noqa: ANN202
    wi = ENGINE.GetCurrentWorldInfo()
    me = _try(lambda: get_pc().Pawn, None)
    p = wi.PawnList
    while p is not None:
        if "PlayerPawn" in str(p.Class.Name) and p != me:
            return p
        p = _try(lambda q=p: q.NextPawn, None)
    return None


def _owned(pawn, mgr) -> list:  # noqa: ANN001
    out = []
    for cls in INV_CLASSES:
        for inv in _try(lambda c=cls: list(unrealsdk.find_all(c, exact=False)), []):
            if str(inv.Name).startswith("Default__"):
                continue
            if any(_try(lambda i=inv, a=a: getattr(i, a), None) in (pawn, mgr) for a in ("Owner", "Instigator", "InvManager")):
                out.append(inv)
    return out


def main() -> None:
    lines.append(f"probe_backpack {time.strftime('%H:%M:%S')}, NetMode {_try(lambda: ENGINE.GetCurrentWorldInfo().NetMode)}")
    pawn = _friend()
    if pawn is None:
        lines.append("no other player here")
        OUT.write_text("\n".join(lines), encoding="utf-8")
        return
    mgr = _try(lambda: pawn.InvManager, None)
    lines.append(f"friend {_try(lambda: pawn.PlayerReplicationInfo.PlayerName)!r}")
    _dump("their inventory manager (non-empty properties)", mgr)
    _dump("their controller (inventory-ish fields)", _try(lambda: pawn.Controller, None), PC_KEYS)
    lines.append("== inventory objects owned by them")
    for inv in _owned(pawn, mgr):
        lines.append(f"   {inv.Class.Name:30s} '{_try(lambda i=inv: i.GetShortHumanReadableName(), '?')}'"
                     f" slot={_try(lambda i=inv: i.QuickSelectSlot, '-')} location={_try(lambda i=inv: i.ItemLocation, '-')}"
                     f" bDeleteMe={_try(lambda i=inv: i.bDeleteMe, '-')}")
    lines.append("== samples (changes only): pick up an item, then drop one")
    OUT.write_text("\n".join(lines), encoding="utf-8")

    hook_func, hook_id = "WillowGame.WillowGameViewportClient:PostRender", "helios_probe_backpack"
    remove_hook(hook_func, Type.POST, hook_id)
    t0, state = time.monotonic(), {"next": 0.0, "last": ""}

    def tick(obj, args, ret, func):  # noqa: ANN001, ANN202, ARG001
        now = time.monotonic()
        if now - t0 > SAMPLE_FOR:
            remove_hook(hook_func, Type.POST, hook_id)
            lines.append("== done")
            OUT.write_text("\n".join(lines), encoding="utf-8")
            print(f"[probe_backpack] done -> {OUT}")
            return
        if now < state["next"]:
            return
        state["next"] = now + SAMPLE_EVERY
        m = _try(lambda: pawn.InvManager, None)
        backpack = _try(lambda: list(m.Backpack), [])
        sample = (f"Backpack={len(backpack) if isinstance(backpack, list) else backpack}"
                  f" BackpackInventoryCount={_try(lambda: m.BackpackInventoryCount)}"
                  f" items={[_try(lambda i=i: i.GetShortHumanReadableName(), '?') for i in backpack][:6] if isinstance(backpack, list) else ''}")
        if sample != state["last"]:
            state["last"] = sample
            lines.append(f"  {now - t0:6.1f}s  {sample}")
            OUT.write_text("\n".join(lines), encoding="utf-8")

    add_hook(hook_func, Type.POST, hook_id, tick)
    print(f"[probe_backpack] sampling for {SAMPLE_FOR:.0f}s - have your friend pick up an item, then drop one")


try:
    main()
except Exception as ex:  # noqa: BLE001
    lines.append(f"probe failed: {type(ex).__name__}: {ex}")
    OUT.write_text("\n".join(lines), encoding="utf-8")
