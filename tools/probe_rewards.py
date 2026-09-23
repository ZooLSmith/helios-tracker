# Dev probe (in game), instant: how the game turns a mission's Reward (attribute-based XP / cash
# multipliers, reward items / pools) into the numbers its mission screen shows. Lists every
# function about rewards on the classes that could compute them (with their parameters), dumps
# the tracked mission's Reward in full, and tries evaluating its attribute values.
# Writes E:\Projects\python\bl2-helios-tracker\tools\probe_rewards.txt (appends)
#   py exec(open(r"E:\Projects\python\bl2-helios-tracker\tools\probe_rewards.py").read())
import enum
import re
from pathlib import Path

import unrealsdk
from mods_base import get_pc

OUT = Path(r"E:\Projects\python\bl2-helios-tracker\tools\probe_rewards.txt")
CLASSES = ("MissionTracker", "MissionDefinition", "WillowPlayerController", "WillowPlayerPawn", "WillowGameInfo",
           "WillowCoopGameInfo", "WillowPlayerReplicationInfo", "AttributeDefinition", "AttributeInitializationDefinition",
           "WillowGlobals", "GlobalsDefinition", "WillowHUDGFxMovie", "MissionStatusPlayerGFxObject", "WillowGFxMenuMissionLog",
           "MissionLogGFxObject", "StatusMenuExGFxMovie")
PATTERN = re.compile(r"reward|experience|\bxp|credit|currency|value|evaluat|mission", re.I)

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
        return f"{type(value).__name__}.{value.name}"
    if depth > 5:
        return "..."
    if hasattr(value, "_type") and hasattr(value._type, "_fields"):  # WrappedStruct
        parts = [f"{f.Name}={_try(lambda f=f: _brief(value._get_field(f), depth + 1))}"
                 for f in _try(lambda: list(value._type._fields()), []) if f.Class.Name.endswith("Property")]
        return "{" + ", ".join(parts) + "}"
    if hasattr(value, "_path_name") and hasattr(value, "Class"):
        return f"{value.Class.Name}'{_try(value._path_name)}'"
    if hasattr(value, "__len__") and not isinstance(value, (str, bytes)):
        return "[" + ", ".join(_brief(v, depth + 1) for v in list(value)[:10]) + "]"
    if isinstance(value, float):
        return f"{value:.4f}"
    return repr(value)


def _functions(class_name: str) -> None:
    cls = _try(lambda: unrealsdk.find_class(class_name), None)
    if cls is None or isinstance(cls, str):
        lines.append(f"== {class_name}: not found")
        return
    lines.append(f"== {class_name}")
    c = cls
    while c is not None and c.Name not in ("Object", "Actor"):
        for f in _try(lambda c=c: list(c._fields()), []):
            if f.Class.Name == "Function" and PATTERN.search(str(f.Name)):
                params = [f"{p.Class.Name.removesuffix('Property')} {p.Name}" for p in _try(lambda f=f: list(f._fields()), [])]
                lines.append(f"   {c.Name}.{f.Name}({', '.join(params)})")
        c = c.SuperField


def main() -> None:
    lines.append("#" * 60)
    for name in CLASSES:
        _functions(name)
    tracker = next((t for t in unrealsdk.find_all("MissionTracker", exact=False) if not t.Name.startswith("Default__")), None)
    active = _try(lambda: tracker.ActiveMission, None)
    lines.append(f"tracked: {_brief(active)} {_try(lambda: str(active.MissionName), '')!r}")
    if active is None:
        return
    lines.append(f"Reward = {_brief(_try(lambda: active.Reward, None))}")
    lines.append(f"AlternativeReward = {_brief(_try(lambda: active.AlternativeReward, None))}")
    pc = get_pc()
    # Attribute values: try the likely evaluation calls on the XP / cash attributes (context: the player)
    for label, attr in (("XP", _try(lambda: active.Reward.ExperienceRewardPercentage.BaseValueAttribute, None)),
                        ("Cash", _try(lambda: active.Reward.CreditRewardMultiplier.BaseValueAttribute, None))):
        lines.append(f"-- {label} attribute {_brief(attr)}")
        if attr is None or isinstance(attr, str):
            continue
        for fn in ("GetValue", "GetBaseValue", "EvaluateAttribute"):
            for args in ((pc,), (pc.Pawn,) if pc else (), ()):
                lines.append(f"   {fn}({_brief(args[0]) if args else ''}) = {_try(lambda fn=fn, args=args: _brief(getattr(attr, fn)(*args)))}")
        lines.append(f"   fields: {_try(lambda: [f.Name for f in attr.Class._fields() if f.Class.Name != 'Function'])}")


try:
    main()
except Exception as ex:  # noqa: BLE001
    lines.append(f"probe failed: {type(ex).__name__}: {ex}")
with OUT.open("a", encoding="utf-8") as fh:
    fh.write("\n".join(lines) + "\n")
print(f"probe_rewards: {len(lines)} lines -> {OUT}")
