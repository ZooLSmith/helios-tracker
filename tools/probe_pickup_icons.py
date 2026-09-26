# Dev probe (in game), at once: the pickups' own icons (not Flash: the textures the game shows for them - .agent/notes.md
# "Ground pickups": PickupFlagIcon, fx_shared_items.Textures.ItemCards.Health / Credits / Ammo_<type>), one per kind and
# ammo type in the level: the item definition, its PickupFlagIcon's object path, size, format - and the other texture
# properties of the definition / pickup (in case the icon is elsewhere for some). Property reads only (no game calls).
# Stand near cash, eridium, health and a few ammo types. Then, offline, tools/extract_pickup_icons.py writes them as
# PNGs to _work/pickup_icons/ (gitignored: nothing from the game in the repo).
# Writes tools/probe_pickup_icons.txt (overwrites)
#   py exec(open(r"<repo>\tools\probe_pickup_icons.py").read())
import sys
from pathlib import Path

MOD = sys.modules["helios_tracker"]
OUT = Path(MOD.__file__).resolve().parents[1] / "tools" / "probe_pickup_icons.txt"
col = MOD._collector  # noqa: SLF001
util = MOD.util
lines: list[str] = []


def _get(obj, name):  # noqa: ANN001, ANN202
    try:
        return getattr(obj, name)
    except Exception as ex:  # noqa: BLE001
        return f"<{type(ex).__name__}>"


def _tex(t) -> str:  # noqa: ANN001
    if t is None or isinstance(t, str):
        return str(t)
    try:
        path = t._path_name()
    except Exception as ex:  # noqa: BLE001
        path = f"<{type(ex).__name__}>"
    return f"{path} [{_get(_get(t, 'Class'), 'Name')}] {_get(t, 'SizeX')}x{_get(t, 'SizeY')} {getattr(_get(t, 'Format'), 'name', _get(t, 'Format'))}"


def _textures(obj, label: str) -> None:  # noqa: ANN001
    """Its object properties pointing at a texture (reads only)."""
    try:
        props = list(obj.Class._fields())
    except Exception:  # noqa: BLE001
        return
    for prop in props:
        if str(_get(_get(prop, "Class"), "Name")) != "ObjectProperty":
            continue
        name = str(_get(prop, "Name"))
        value = _get(obj, name)
        if value is not None and not isinstance(value, str) and "Texture" in str(_get(_get(value, "Class"), "Name")):
            lines.append(f"  {label}.{name} = {_tex(value)}")


seen: set[str] = set()
for key, ptr in list(col._pickups.items()):  # noqa: SLF001
    p = ptr()
    if p is None:
        continue
    inv = _get(p, "Inventory")
    if inv is None or isinstance(inv, str):
        continue
    kind = util.pickup_kind(inv)
    definition = _get(_get(inv, "DefinitionData"), "ItemDefinition")
    tag = f"{kind}:{_get(definition, 'Name')}" if kind == "ammo" else str(kind)
    if not kind or tag in seen:
        continue
    seen.add(tag)
    lines.append(f"\n== {tag}: {_get(inv, 'Name')} [{_get(_get(inv, 'Class'), 'Name')}]")
    lines.append(f"  PickupFlagIcon = {_tex(_get(definition, 'PickupFlagIcon'))}")
    _textures(definition, "definition")
    _textures(p, "pickup")
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"probe_pickup_icons: written {OUT} ({sorted(seen)})")
