# Dev probe (in game), instant, read-only: where Borderlands 1 keeps the player's class / character name as the game
# shows it - the page says "Mordecai ?" (the class definition's object name, a guess: BL2's player info ->
# CharacterNameIdDef -> CharacterClassId -> LocalizedClassNameNonCaps isn't in BL1 - inspector._class_name_uncached).
# 1. every text property (strings, names) of the controller's PlayerClass, the player info, the controller - and of the
#    objects they point to, one level down (the class's own definitions: its skill set, its identifiers...);
# 2. the functions of those classes named like a name / a class / a character (listed, never called).
# Writes tools/probes/probe_player_text.txt (overwrites)
#   py exec(open(r"<repo>\tools\probes\probe_player_text.py").read())
import re
import sys
from pathlib import Path

from mods_base import get_pc

OUT = Path(sys.modules["helios_tracker"].__file__).resolve().parents[1] / "tools" / "probes" / "probe_player_text.txt"  # the repo, through the mod's junction
TEXT = {"StrProperty", "NameProperty"}
FUNCTIONS = re.compile(r"name|class|character|title|display|caption|text", re.I)
SKIP_LINKS = re.compile(r"^(Outer|Class|ObjectArchetype|Owner|Base|Instigator|Pawn|Controller|PlayerReplicationInfo|Next|"
                        r"Previous|WorldInfo|myHUD|PlayerInput|ViewTarget|Player)$")
lines: list[str] = []


def _try(fn, default="<err>"):  # noqa: ANN001, ANN202
    try:
        return fn()
    except Exception as ex:  # noqa: BLE001
        return f"<{type(ex).__name__}>" if default == "<err>" else default


def _flush() -> None:
    with OUT.open("a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    lines.clear()


def _chain(cls):  # noqa: ANN001, ANN202
    out, c = [], cls
    while c is not None and not isinstance(c, str) and str(c.Name) != "Object":
        out.append(c)
        c = _try(lambda c=c: c.SuperField, None)
    return out


def _texts(label: str, obj, follow: bool, seen: set) -> None:  # noqa: ANN001
    if obj is None or isinstance(obj, str) or not hasattr(obj, "Class"):
        lines.append(f"== {label}: None")
        return
    key = _try(lambda: obj._get_address(), id(obj))
    if key in seen:
        return
    seen.add(key)
    lines.append(f"== {label}: {obj.Class.Name}'{_try(obj._path_name, obj.Name)}'")
    empty, linked = [], []
    for c in _chain(obj.Class):
        for f in _try(lambda c=c: list(c._fields()), []) or []:
            kind = str(f.Class.Name)
            if kind in TEXT:
                value = str(_try(lambda f=f: obj._get_field(f), ""))
                if value and value != "None":
                    lines.append(f"   {c.Name}.{f.Name} = {value!r}")
                else:
                    empty.append(str(f.Name))
            elif follow and kind == "ObjectProperty" and not SKIP_LINKS.match(str(f.Name)):
                target = _try(lambda f=f: obj._get_field(f), None)
                if target is not None and not isinstance(target, str) and hasattr(target, "Class"):
                    linked.append((f"{label}.{f.Name}", target))
    if empty:
        lines.append(f"   (empty: {', '.join(sorted(set(empty))[:50])})")
    _flush()
    for sub_label, target in linked[:30]:
        _texts(sub_label, target, False, seen)


def _functions(label: str, cls) -> None:  # noqa: ANN001
    found = sorted({str(f.Name) for c in _chain(cls)[:3] for f in _try(lambda c=c: list(c._fields()), []) or []
                    if str(f.Class.Name) == "Function" and FUNCTIONS.search(str(f.Name))})
    lines.append(f"== {label}'s functions named like a name / class (its 3 nearest classes; listed, not called): {len(found)}")
    lines.extend(f"   {name}()" for name in found)
    _flush()


OUT.write_text("", encoding="utf-8")
pc = get_pc()
player_class = _try(lambda: pc.PlayerClass, None)
pri = _try(lambda: pc.PlayerReplicationInfo, None)
seen_objects: set = set()
_texts("PlayerClass", player_class, True, seen_objects)
_texts("player info", pri, True, seen_objects)
_texts("class default", _try(lambda: player_class.Class.ClassDefaultObject, None), False, seen_objects)
lines.append(f"== controller's CharacterName-like fields: PlayerClass.CharacterName = {_try(lambda: player_class.CharacterName)}")
_flush()
for label, obj in (("PlayerClass", player_class), ("player info", pri), ("controller", pc)):
    if obj is not None and not isinstance(obj, str):
        _functions(label, obj.Class)
print(f"[probe_player_text] -> {OUT}")
