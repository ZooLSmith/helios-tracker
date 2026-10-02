# Dev probe (in game), instant: where the player's localized class name ("Gunzerker") is.
# Writes tools/probes/probe_class.txt (appends)
#   py exec(open(r"<repo>\tools\probes\probe_class.py").read())
import sys
from pathlib import Path

from mods_base import get_pc

OUT = Path(sys.modules["helios_tracker"].__file__).resolve().parents[1] / "tools" / "probes" / "probe_class.txt"  # the repo, through the mod's junction


def _try(fn):  # noqa: ANN001, ANN202
    try:
        v = fn()
        return f"{v.Class.Name}'{v._path_name()}'" if hasattr(v, "_path_name") else repr(v)
    except Exception as ex:  # noqa: BLE001
        return f"<{type(ex).__name__}: {ex}>"


def _dump(obj, label: str) -> None:  # noqa: ANN001
    lines.append(f"== {label}: {_try(lambda: obj)}")
    if not hasattr(obj, "Class"):
        return
    c = obj.Class
    while c is not None and c.Name not in ("Object", "GBXDefinition"):
        for f in c._fields():
            if f.Class.Name in ("StrProperty", "ObjectProperty", "NameProperty"):
                lines.append(f"   {c.Name}.{f.Name} = {_try(lambda f=f: obj._get_field(f))}")
        c = c.SuperField


pc = get_pc()
pri = pc.PlayerReplicationInfo
lines: list[str] = ["#" * 60]
lines.append(f"pri.CharacterNameIdDef = {_try(lambda: pri.CharacterNameIdDef)}")
lines.append(f"pc.PlayerClass = {_try(lambda: pc.PlayerClass)}")
_dump(pri.CharacterNameIdDef, "PRI CharacterNameIdDef")
_dump(pc.PlayerClass, "PlayerClass")
ident = pc.PlayerClass.CharacterNameId if hasattr(pc.PlayerClass, "CharacterNameId") else None
_dump(ident, "PlayerClass.CharacterNameId")
with OUT.open("a", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")
print("\n".join(lines[:6]))
