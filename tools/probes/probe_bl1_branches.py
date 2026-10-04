# Dev probe (in game), instant: Borderlands 1's skill branch names, the game's own chain (.agent/bl1.md). Offline:
# SkillTreeGFxHelper.Flash_SetCharacter sends the status menu's skill clip to the frame GetCharacterName() returns (a
# switch on CurrentCharacter, a GlobalsDefinition.CharacterNames like PlayerClass.CharacterName: 0 roland, 1 mordecai,
# 2 lilith, 3 brick); that frame's ActionScript sets tree1..3 to "$<StringAliasMap:skills_hunter_branch1>"...;
# DefaultGame.ini's alias map: skills_hunter_branch1 -> "<Strings:WillowGame.SkillTreeMovie.SkillsHunterBranch1String>"
# -> WillowGame.int's SNIPER. Checked here, the calls the mod would make:
# 1. the player's class CharacterName; any live SkillTreeGFxHelper (its CurrentCharacter, GetCharacterName());
# 2. a SkillTreeGFxHelper constructed by us, CurrentCharacter = the class's CharacterName, GetCharacterName() (a pure
#    switch in script);
# 3. the WillowUIDataStore_StringAliasMap objects: their skills_* entries (MenuInputMapArray), GetStringWithFieldName;
# 4. Object.Localize("SkillTreeMovie", "SkillsHunterBranch1String", "WillowGame") and the class string.
# Writes tools/probes/probe_bl1_branches.txt (appends), after each section.
#   py exec(open(r"<repo>\tools\probes\probe_bl1_branches.py").read())
from enum import Enum
import sys
from pathlib import Path

import unrealsdk


def _out() -> Path:
    if (mod := sys.modules.get("helios_tracker")) is not None and getattr(mod, "__file__", None):
        return Path(mod.__file__).resolve().parents[1] / "tools" / "probes" / "probe_bl1_branches.txt"
    for entry in sys.path:
        if (link := Path(entry) / "helios_tracker").is_dir():
            return link.resolve().parent / "tools" / "probes" / "probe_bl1_branches.txt"
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
cls = _try(lambda: pc.PlayerClass, None)
char = _try(lambda: cls.CharacterName, None)

# 1. the class; live helpers
lines.append(f"== class {_try(lambda: cls._path_name())}: CharacterName {_enum(char)}")
for h in _try(lambda: list(unrealsdk.find_all("SkillTreeGFxHelper", exact=False)), []) or []:
    lines.append(f"   live {_try(lambda h=h: h._path_name())}: CurrentCharacter {_enum(_try(lambda h=h: h.CurrentCharacter))}, "
                 f"GetCharacterName() {_try(lambda h=h: h.GetCharacterName())!r}")
_flush()

# 2. one of our own
helper = _try(lambda: unrealsdk.construct_object("SkillTreeGFxHelper", pc), None)
lines.append(f"== constructed: {_try(lambda: helper._path_name())}")
if helper is not None and not isinstance(helper, str):
    lines.append(f"   set CurrentCharacter: {_try(lambda: setattr(helper, 'CurrentCharacter', char))}, now {_enum(_try(lambda: helper.CurrentCharacter))}")
    lines.append(f"   GetCharacterName() {_try(lambda: helper.GetCharacterName())!r}")
    for n in range(4):
        lines.append(f"   CurrentCharacter={n}: {_try(lambda n=n: (setattr(helper, 'CurrentCharacter', n), helper.GetCharacterName())[1])!r}")
_flush()

# 3. the alias map
for store in _try(lambda: list(unrealsdk.find_all("WillowUIDataStore_StringAliasMap", exact=False)), []) or []:
    entries = _try(lambda s=store: list(s.MenuInputMapArray), [])
    lines.append(f"== alias map {_try(lambda s=store: s._path_name())}: {len(entries) if isinstance(entries, list) else entries} entries")
    for e in entries if isinstance(entries, list) else []:
        if str(_try(lambda e=e: e.FieldName, "")).startswith("skills_"):
            lines.append(f"   {_try(lambda e=e: e.FieldName)} [{_try(lambda e=e: e.Set)}] -> {_try(lambda e=e: e.MappedText)!r}")
    lines.append(f"   GetStringWithFieldName('skills_hunter_branch1') {_try(lambda s=store: s.GetStringWithFieldName('skills_hunter_branch1'))!r}")
_flush()

# 4. Localize
obj = _try(lambda: unrealsdk.find_class("Object").ClassDefaultObject, None)
for key in ("SkillsHunterBranch1String", "SkillsHunterBranch2String", "SkillsHunterBranch3String", "SkillsHunterClassString"):
    lines.append(f"== Localize SkillTreeMovie.{key}: {_try(lambda k=key: obj.Localize('SkillTreeMovie', k, 'WillowGame'))!r}")
_flush()
