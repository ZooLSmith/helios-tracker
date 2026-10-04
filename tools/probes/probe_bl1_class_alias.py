# Dev probe (in game), instant, read-only: Borderlands 1's class name as its menus show it ("Hunter" on the main menu;
# the page says "Mordecai ?" - probe_player_text.txt: no property holds it). Its menus' texts come through the string
# alias map (bl1.md "skill branch names": "$<StringAliasMap:skills_hunter_branch1>" -> "<Strings:WillowGame.Section.Key>",
# localized) - the class's likely the same. Lists the alias map's entries (WillowUIDataStore_StringAliasMap's default
# object, MenuInputMapArray: FieldName -> MappedText) that mention a class / a character - a property read, nothing
# called - and each one's localized text when it's a <Strings:...> reference (Object.Localize on that reference: the
# call branch_names already makes, games.py).
# Writes tools/probes/probe_bl1_class_alias.txt (overwrites)
#   py exec(open(r"<repo>\tools\probes\probe_bl1_class_alias.py").read())
import re
import sys
from pathlib import Path

import unrealsdk

OUT = Path(sys.modules["helios_tracker"].__file__).resolve().parents[1] / "tools" / "probes" / "probe_bl1_class_alias.txt"  # the repo, through the mod's junction
WORDS = re.compile(r"hunter|mordecai|soldier|roland|siren|lilith|berserker|brick|class|char", re.I)
STRINGS = re.compile(r"<Strings:([^.>]+)\.([^.>]+)\.([^>]+)>")
lines: list[str] = []


def _try(fn, default="<err>"):  # noqa: ANN001, ANN202
    try:
        return fn()
    except Exception as ex:  # noqa: BLE001
        return f"<{type(ex).__name__}: {ex}>"[:160] if default == "<err>" else default


aliases = _try(lambda: list(unrealsdk.find_class("WillowUIDataStore_StringAliasMap").ClassDefaultObject.MenuInputMapArray), [])
localize = _try(lambda: unrealsdk.find_class("Object").ClassDefaultObject.Localize, None)
lines.append(f"== the alias map: {len(aliases) if isinstance(aliases, list) else aliases} entries; the ones mentioning a class / character:")
for entry in aliases if isinstance(aliases, list) else []:
    field, text = str(_try(lambda e=entry: e.FieldName, "")), str(_try(lambda e=entry: e.MappedText, ""))
    if not (WORDS.search(field) or WORDS.search(text)):
        continue
    shown = ""
    if (m := STRINGS.fullmatch(text)) and localize is not None and not isinstance(localize, str):
        package, section, key = m.groups()
        shown = f"  -> {_try(lambda: str(localize(section, key, package)))!r}"
    lines.append(f"   {field} = {text}{shown}")
OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"[probe_bl1_class_alias] -> {OUT}")
