# Dev probe (in game), instant: how much XP discovering an area gives, and what else the game knows
# about an area. Logs:
#  - the parameters of the discovery functions (the controller's award / handle functions, the area's
#    level / game stage getters) - what the XP is computed from;
#  - the area's level-ish getters called (GetExpLevel, GetGameStage, GetAwesomeLevel...) - reads only;
#  - the globals' fields (GlobalsDefinition, WillowGlobals, the game info) whose name looks XP /
#    discovery / exploration related - a base discovery reward and its scaling;
#  - the SeqEvent_WorldDiscoveryArea events of the level (the Kismet hooks an area fires);
#  - the challenges named like discovery / exploration (the "explore every area" ones).
# Writes tools/probe_discovery_xp.txt (overwrites)
#   py exec(open(r"<repo>\tools\probe_discovery_xp.py").read())
import enum
import re
import sys
from pathlib import Path

import unrealsdk
from mods_base import ENGINE, get_pc

OUT = Path(sys.modules["helios_tracker"].__file__).resolve().parents[1] / "tools" / "probe_discovery_xp.txt"  # the repo, through the mod's junction
PATTERN = re.compile(r"discover|explor|worldarea|exp(erience)?(reward|scale|multiplier|level)|xp", re.I)
lines: list[str] = []


def _try(fn, default="<err>"):  # noqa: ANN001, ANN202
    try:
        return fn()
    except Exception as ex:  # noqa: BLE001
        return f"<{type(ex).__name__}: {ex}>" if default == "<err>" else default


def _brief(value, depth: int = 0) -> str:  # noqa: ANN001
    if value is None:
        return "None"
    if isinstance(value, enum.Enum):
        return value.name
    if isinstance(value, float):
        return f"{value:.3f}"
    if hasattr(value, "_path_name") and hasattr(value, "Class"):
        return f"{value.Class.Name}'{_try(value._path_name)}'"
    if depth > 2:
        return "..."
    if hasattr(value, "_type") and hasattr(value._type, "_fields"):
        return "{" + ", ".join(f"{f.Name}={_try(lambda f=f: _brief(value._get_field(f), depth + 1))}"
                               for f in _try(lambda: list(value._type._fields()), []) if f.Class.Name.endswith("Property")) + "}"
    if hasattr(value, "__len__") and not isinstance(value, (str, bytes)):
        items = list(value)
        return f"(len {len(items)}) [" + ", ".join(_brief(v, depth + 1) for v in items[:8]) + "]"
    return repr(value)


def _signature(func) -> str:  # noqa: ANN001
    params = [f"{p.Name}:{p.Class.Name.replace('Property', '')}" for p in _try(lambda: list(func._fields()), [])
              if p.Class.Name.endswith("Property")]
    return f"{func.Name}({', '.join(params)})"


def _functions(cls, pattern) -> None:  # noqa: ANN001
    c = cls
    while c is not None and c.Name != "Object":
        for f in _try(lambda c=c: list(c._fields()), []):
            if f.Class.Name == "Function" and pattern.search(str(f.Name)):
                lines.append(f"   {c.Name}.{_signature(f)}")
        c = c.SuperField


def _matching_fields(obj, label: str) -> None:  # noqa: ANN001
    lines.append(f"== {label}: {_brief(obj)}")
    c = _try(lambda: obj.Class, None)
    while c is not None and not isinstance(c, str) and c.Name != "Object":
        for f in _try(lambda c=c: list(c._fields()), []):
            if f.Class.Name.endswith("Property") and PATTERN.search(str(f.Name)):
                lines.append(f"   {c.Name}.{f.Name} = {_try(lambda f=f: _brief(obj._get_field(f)))}")
        c = c.SuperField


def main() -> None:
    pc = get_pc()
    wi = ENGINE.GetCurrentWorldInfo()
    areas = [a for a in unrealsdk.find_all("WorldDiscoveryArea", exact=False) if not a.Name.startswith("Default__")]
    lines.append(f"map: {wi.GetStreamingPersistentMapName()}, player level {_try(lambda: pc.PlayerReplicationInfo.ExpLevel)}")
    lines.append("== discovery functions (signatures)")
    _functions(pc.Class, re.compile(r"discover|explor|worldarea", re.I))
    if areas:
        _functions(areas[0].Class, re.compile(r"level|stage|name|exp|award|discover", re.I))
    lines.append("== the areas' getters")
    for a in areas:
        vals = {g: _try(lambda g=g, a=a: _brief(getattr(a, g)())) for g in
                ("GetExpLevel", "GetGameStage", "GetAwesomeLevel", "GetExpLevelForEquip", "GetWorldAreaShortName")}
        lines.append(f"   {a.Name} {str(a.WorldAreaDisplayName)!r}: {vals} multiplier={_brief(a.ExperienceRewardMultiplier)}")
    for label, obj in {"GameInfo": _try(lambda: wi.Game, None), "GRI": _try(lambda: wi.GRI, None),
                       "pc": pc, "PRI": _try(lambda: pc.PlayerReplicationInfo, None)}.items():
        if obj is not None and not isinstance(obj, str):
            _matching_fields(obj, label)
    for cls in ("GlobalsDefinition", "WillowGlobals", "ExperienceResourcePool", "GameBalanceDefinition"):
        for obj in _try(lambda cls=cls: list(unrealsdk.find_all(cls, exact=False)), [])[:4]:
            _matching_fields(obj, cls)
    events = _try(lambda: list(unrealsdk.find_all("SeqEvent_WorldDiscoveryArea", exact=False)), [])
    lines.append(f"== {len(events)} SeqEvent_WorldDiscoveryArea")
    for e in events[:6]:
        lines.append(f"   {_brief(e)} originator={_brief(_try(lambda e=e: e.Originator, None))}")
    challenges = [c for c in _try(lambda: list(unrealsdk.find_all("ChallengeDefinition", exact=False)), [])
                  if re.search(r"discover|explor", str(c.Name), re.I)]
    lines.append(f"== {len(challenges)} discovery / exploration challenges")
    for c in challenges[:12]:
        lines.append(f"   {_brief(c)}")


try:
    main()
except Exception as ex:  # noqa: BLE001
    lines.append(f"probe failed: {type(ex).__name__}: {ex}")
OUT.write_text("\n".join(lines), encoding="utf-8")
print(f"probe_discovery_xp: {len(lines)} lines -> {OUT}")
