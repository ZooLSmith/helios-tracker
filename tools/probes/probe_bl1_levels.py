# Dev probe (in game), instant, read-only: Borderlands 1's item levels - the page shows inv.ExpLevel (6 on weapons
# whose card says level 4, the user). BL1's card (InventoryCardGFx.SetWeaponCard...: native) - what it reads isn't in
# script; the candidates: DefinitionData's ManufacturerGradeIndex / GameStage..., the item's own level fields.
# For each of the player's items (equipped and backpack): its name, ExpLevel, every DefinitionData field, its own
# int fields with "level" / "grade" / "stage" in their name; the signatures of its level / tech functions (not called).
# Writes tools/probes/probe_bl1_levels.txt (appends).
#   py exec(open(r"<repo>\tools\probes\probe_bl1_levels.py").read())
from enum import Enum
import sys
from pathlib import Path

import unrealsdk


def _out() -> Path:
    if (mod := sys.modules.get("helios_tracker")) is not None and getattr(mod, "__file__", None):
        return Path(mod.__file__).resolve().parents[1] / "tools" / "probes" / "probe_bl1_levels.txt"
    for entry in sys.path:
        if (link := Path(entry) / "helios_tracker").is_dir():
            return link.resolve().parent / "tools" / "probes" / "probe_bl1_levels.txt"
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
        return f"<{type(ex).__name__}: {ex}>"[:200] if default == "<err>" else default


def _enum(value) -> str:  # noqa: ANN001
    return f"{value.name} ({int(value)})" if isinstance(value, Enum) else repr(value)


mods_base = __import__("mods_base")
pc = _try(lambda: mods_base.get_pc(), None)
pawn = _try(lambda: pc.Pawn, None)
inv_manager = _try(lambda: pawn.InvManager, None)
items = []
for getter in (lambda: inv_manager.InventoryChain, lambda: inv_manager.ItemChain):
    item = _try(getter, None)
    while item is not None and not isinstance(item, str) and len(items) < 40:
        items.append(item)
        item = _try(lambda i=item: i.Inventory, None)
for item in _try(lambda: list(inv_manager.Backpack), []) or []:
    items.append(item)
lines.append(f"== {len(items)} items (player level {_try(lambda: pc.PlayerReplicationInfo.ExpLevel)})")
_flush()
for item in items:
    lines.append(f"-- {_try(lambda: item.Class.Name)} {_try(lambda: item.GetShortHumanReadableName())!r}: ExpLevel {_try(lambda: item.ExpLevel)}")
    data = _try(lambda: item.DefinitionData, None)
    if data is not None and not isinstance(data, str):
        parts = []
        for f in _try(lambda: list(data._type._fields()), []) or []:
            if f.Class.Name.endswith("Property"):
                v = _try(lambda f=f: data._get_field(f))
                parts.append(f"{f.Name}={getattr(v, '_path_name', lambda: v)()}")
        lines.append("   DefinitionData: " + ", ".join(map(str, parts)))
    own = []
    for f in _try(lambda: list(item.Class._fields()), []) or []:
        name = str(f.Name)
        low = name.lower()
        if any(k in low for k in ("level", "grade", "stage", "tech")):
            if f.Class.Name.endswith("Property"):
                own.append(f"{name}={_try(lambda f=f: item._get_field(f))}")
            elif f.Class.Name == "Function":
                params = [str(p.Name) for p in _try(lambda f=f: list(f._fields()), []) or []]
                own.append(f"{name}({', '.join(params)})")
    lines.append("   own: " + ", ".join(own))
    _flush()
