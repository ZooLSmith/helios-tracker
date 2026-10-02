# Dev probe (in game), instant, reads only (no function calls on game objects): what the game has for
# item serials / Gibbed codes - the asset library (sublibraries of each group's parts, the save format's
# indexes), classes / structs / functions named after serials or packed data, and where the held weapon's
# parts sit in those libraries (to compare with Gibbed's indexes).
# Hold a weapon when running it (BL2 and the Pre-Sequel both).
# Writes tools/probes/probe_serial.txt (rewritten after each section)
#   py exec(open(r"<repo>\tools\probes\probe_serial.py").read())
import re
import sys
from enum import Enum
from pathlib import Path

import unrealsdk
from mods_base import get_pc

OUT = Path(sys.modules["helios_tracker"].__file__).resolve().parents[1] / "tools" / "probes" / "probe_serial.txt"  # the repo, through the mod's junction
PATTERN = re.compile(r"AssetLibrar|Sublibrar|Serial|Packed|AssetIndex|AssetRef", re.I)
FULL_INSTANCES = 3  # instances of a matching class dumped in full (the rest counted)

lines: list[str] = []


def _save() -> None:
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _try(fn, default="<err>"):  # noqa: ANN001, ANN202
    try:
        return fn()
    except Exception as ex:  # noqa: BLE001
        return f"<{type(ex).__name__}: {ex}>" if default == "<err>" else default


def _brief(value, depth: int = 0) -> str:  # noqa: ANN001
    if value is None:
        return "None"
    if isinstance(value, Enum):
        return str(value.name)
    if isinstance(value, (str, int, bool)):
        return repr(value) if isinstance(value, str) else str(value)
    if isinstance(value, float):
        return f"{value:.3f}"
    if depth > 3:
        return "..."
    if hasattr(value, "_type"):  # WrappedStruct
        return "{" + ", ".join(f"{f.Name}={_brief(_try(lambda f=f: value._get_field(f)), depth + 1)}"
                               for f in _try(lambda: list(value._type._fields()), [])
                               if f.Class.Name.endswith("Property")) + "}"
    if hasattr(value, "_path_name") and hasattr(value, "Class"):  # UObject
        return _try(value._path_name)
    if hasattr(value, "__len__"):  # WrappedArray
        items = list(value)
        return "[" + ", ".join(_brief(v, depth + 1) for v in items[:6]) + (f", ... ({len(items)} total)" if len(items) > 6 else "") + "]"
    return repr(value)


def _params(func) -> str:  # noqa: ANN001
    return ", ".join(f"{p.Name}:{p.Class.Name}" for p in _try(lambda: list(func._fields()), []))


def _flags(func) -> str:  # noqa: ANN001
    flags = _try(lambda: int(func.FunctionFlags), 0)
    return " ".join(n for bit, n in ((0x400, "native"), (0x2000, "static"), (0x2, "final")) if flags & bit)


def _own_fields(struct, indent: str) -> None:  # noqa: ANN001
    for f in _try(lambda: list(struct._fields()), []):
        if f.Class.Name == "Function":
            lines.append(f"{indent}fn {f.Name}({_params(f)})  [{_flags(f)}]")
        else:
            inner = _try(lambda f=f: f.Inner.Class.Name, "") if f.Class.Name == "ArrayProperty" else ""
            of = _try(lambda f=f: (f.Inner if inner else f).PropertyClass.Name, "") or _try(lambda f=f: (f.Inner if inner else f).Struct.Name, "")
            lines.append(f"{indent}{f.Name}: {f.Class.Name}{f'<{inner}>' if inner else ''}{f' ({of})' if of else ''}")


def _props(obj, indent: str) -> None:  # noqa: ANN001
    c = _try(lambda: obj.Class, None)
    while c is not None and not isinstance(c, str) and c.Name != "Object":
        for f in _try(lambda c=c: list(c._fields()), []):
            if f.Class.Name.endswith("Property"):
                lines.append(f"{indent}{c.Name}.{f.Name} = {_try(lambda f=f: _brief(obj._get_field(f)))}")
        c = c.SuperField


def main() -> None:  # noqa: C901, PLR0912, PLR0915
    lines.append("== classes named after serials / packed data / the asset library (their own fields)")
    classes = [c for c in unrealsdk.find_all("Class", exact=True) if PATTERN.search(str(c.Name))]
    for c in classes:
        lines.append(f"   class {_try(c._path_name)}  (super {_try(lambda c=c: c.SuperField.Name, None)})")
        _own_fields(c, "      ")
    _save()

    lines.append("== structs named after them")
    for s in unrealsdk.find_all("ScriptStruct", exact=True):
        if PATTERN.search(str(s.Name)):
            lines.append(f"   struct {_try(s._path_name)}")
            _own_fields(s, "      ")
    _save()

    lines.append("== functions named after them (anywhere)")
    for f in unrealsdk.find_all("Function", exact=True):
        if PATTERN.search(str(f.Name)) and not str(f.Name).startswith("Default__"):
            lines.append(f"   {_try(f._path_name)}({_params(f)})  [{_flags(f)}]")
    _save()

    lines.append("== instances of those classes")
    libraries: list = []
    for c in classes:
        found = [o for o in _try(lambda c=c: list(unrealsdk.find_all(c.Name, exact=True)), []) if not o.Name.startswith("Default__")]
        lines.append(f"   {c.Name}: {len(found)} instances")
        for o in found[:FULL_INSTANCES]:
            lines.append(f"    - {_try(o._path_name)}")
            _props(o, "        ")
        if "sublibrar" in str(c.Name).lower():
            libraries += found
        _save()

    lines.append("== objects pointing to an asset library manager (globals, game info)")
    for cls in ("GlobalsDefinition", "WillowGlobals", "GearboxGlobals", "WillowGameInfo"):
        for o in _try(lambda cls=cls: list(unrealsdk.find_all(cls, exact=False)), []):
            if o.Name.startswith("Default__"):
                continue
            c = o.Class
            while c is not None and c.Name != "Object":
                for f in _try(lambda c=c: list(c._fields()), []):
                    if f.Class.Name.endswith("Property") and re.search(r"asset|librar|serial", str(f.Name), re.I):
                        lines.append(f"   {_try(o._path_name)} {c.Name}.{f.Name} = {_try(lambda f=f, o=o: _brief(o._get_field(f)))}")
                c = c.SuperField
    _save()

    lines.append("== the held weapon")
    weapon = _try(lambda: get_pc().Pawn.Weapon, None)
    if weapon is None or isinstance(weapon, str):
        lines.append("   (no weapon held)")
        return
    lines.append(f"   {_try(weapon._path_name)}")
    for c_name in ("WillowWeapon", "WillowInventory", "Inventory"):  # identity-ish fields (unique id, serial...)
        c = _try(lambda n=c_name: unrealsdk.find_class(n), None)
        for f in _try(lambda c=c: list(c._fields()), []):
            if f.Class.Name.endswith("Property") and re.search(r"unique|serial|packed|id$|definitiondata", str(f.Name), re.I):
                lines.append(f"   {c_name}.{f.Name} = {_try(lambda f=f: _brief(weapon._get_field(f)))}")
    data = _try(lambda: weapon.DefinitionData, None)
    parts = []  # (field, object) of DefinitionData's object fields
    for f in _try(lambda: list(data._type._fields()), []):
        v = _try(lambda f=f: data._get_field(f), None)
        if hasattr(v, "_path_name"):
            parts.append((str(f.Name), v))
    _save()

    lines.append("== where each of its parts sits in the sublibraries (object arrays holding it: index)")
    for lib in libraries:  # every object-array field of every sublibrary, searched for the parts
        c = lib.Class
        while c is not None and c.Name != "Object":
            for f in _try(lambda c=c: list(c._fields()), []):
                if f.Class.Name != "ArrayProperty" or _try(lambda f=f: f.Inner.Class.Name, "") != "ObjectProperty":
                    continue
                arr = _try(lambda f=f, lib=lib: list(lib._get_field(f)), [])
                addrs = [_try(lambda o=o: o._get_address(), None) if o is not None else None for o in arr]
                for field, part in parts:
                    a = _try(lambda p=part: p._get_address(), None)
                    if a is not None and a in addrs:
                        lines.append(f"   {field} {_try(part._path_name)}: {_try(lib._path_name)}.{f.Name}[{addrs.index(a)}] (of {len(arr)})")
            c = c.SuperField
    lines.append(f"   ({len(libraries)} sublibraries searched, {len(parts)} object fields in DefinitionData)")


try:
    main()
except Exception as ex:  # noqa: BLE001
    lines.append(f"probe failed: {type(ex).__name__}: {ex}")
_save()
