# Dev probe (in game), instant: where an interactive object's name comes from - the golden chest in
# Sanctuary is named from its class ("Interactive Object ?") as the host, fine as a client. Stand next
# to it (host) and run it; ideally once as a client too.
# Logs: every interactive object within 10 m: class, name, net mode, its definition, its balance
# (BalanceDefinitionState), the balance's DefaultDisplayName, the definition's name-ish fields, and what
# GetTargetName / GetHumanReadableName give (the collector's fallbacks).
# Writes tools/probe_object_names.txt (overwrites)
#   py exec(open(r"<repo>\tools\probe_object_names.py").read())
import enum
import math
import re
import sys
from pathlib import Path

import unrealsdk
from mods_base import ENGINE, get_pc

OUT = Path(sys.modules["helios_tracker"].__file__).resolve().parents[1] / "tools" / "probe_object_names.txt"  # the repo, through the mod's junction
RANGE = 1000.0  # uu (10 m)
PATTERN = re.compile(r"name|display|text|balance|definition|header|title", re.I)
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
    if hasattr(value, "_path_name") and hasattr(value, "Class"):
        return f"{value.Class.Name}'{_try(value._path_name)}'"
    if hasattr(value, "_type") and hasattr(value._type, "_fields"):
        return "{" + ", ".join(f"{f.Name}={_try(lambda f=f: _brief(value._get_field(f)))}"
                               for f in _try(lambda: list(value._type._fields()), []) if f.Class.Name.endswith("Property")) + "}"
    return repr(value)


def _call(fn) -> str:  # noqa: ANN001
    for args in ((), ("",)):
        r = _try(lambda a=args: fn(*a), None)
        if r is not None and not isinstance(r, str) or (isinstance(r, str) and not r.startswith("<")):
            return _brief(r)
    return "<fails>"


def _named_fields(obj, label: str) -> None:  # noqa: ANN001
    c = _try(lambda: obj.Class, None)
    while c is not None and not isinstance(c, str) and c.Name not in ("Object", "Actor", "GBXDefinition"):
        for f in _try(lambda c=c: list(c._fields()), []):
            if f.Class.Name.endswith("Property") and PATTERN.search(str(f.Name)):
                lines.append(f"      {label} {c.Name}.{f.Name} = {_try(lambda f=f: _brief(obj._get_field(f)))}")
        c = c.SuperField


def main() -> None:
    wi = ENGINE.GetCurrentWorldInfo()
    here = get_pc().Pawn.Location
    lines.append(f"map {_try(lambda: str(wi.GetStreamingPersistentMapName()))} netmode={_try(lambda: _brief(wi.NetMode))}")
    for io in unrealsdk.find_all("WillowInteractiveObject", exact=False):
        loc = _try(lambda io=io: io.Location, None)
        if io.Name.startswith("Default__") or loc is None or isinstance(loc, str):
            continue
        d = math.dist((loc.X, loc.Y, loc.Z), (here.X, here.Y, here.Z))
        if d > RANGE:
            continue
        definition = _try(lambda io=io: io.InteractiveObjectDefinition, None)
        balance = _try(lambda io=io: io.BalanceDefinitionState.BalanceDefinition, None)
        lines.append(f"== {io.Class.Name} {io.Name} {d / 100:.1f} m")
        lines.append(f"   definition = {_brief(definition)}")
        lines.append(f"   BalanceDefinitionState = {_try(lambda io=io: _brief(io.BalanceDefinitionState))}")
        lines.append(f"   balance.DefaultDisplayName = {_try(lambda: _brief(balance.DefaultDisplayName))}")
        lines.append(f"   GetTargetName = {_call(io.GetTargetName)}   GetHumanReadableName = {_call(io.GetHumanReadableName)}")
        if definition is not None and not isinstance(definition, str):
            _named_fields(definition, "definition")
        if balance is not None and not isinstance(balance, str):
            _named_fields(balance, "balance")


try:
    main()
except Exception as ex:  # noqa: BLE001
    lines.append(f"probe failed: {type(ex).__name__}: {ex}")
OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"probe_object_names: {len(lines)} lines -> {OUT}")
