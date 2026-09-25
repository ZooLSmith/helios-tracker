# Dev probe (in game), read-only, samples for 60 s: how a hidden helper skill links to its real one -
# Krieg's Blood Overdrive runs as "Blood Overdrive Child" (dev text: "If you are reading this please
# bu[g]..."), shown as is in the Info tab's timed effects. For every distinct active skill definition
# seen in the skill manager (the host's has every player's), dumps once: the Skill instance's fields
# and its definition's every non-empty property - looking for a parent / owner / source link, or a
# flag that marks it hidden. Also: which skill-tree skill (anyone's) names the same definition.
# Trigger Blood Overdrive (or any timed passive) during the 60 s.
# Writes tools/probe_child_skill.txt (overwrites)
#   py exec(open(r"<repo>\tools\probe_child_skill.py").read())
import time
from enum import Enum
import sys
from pathlib import Path

import unrealsdk
from mods_base import get_pc
from unrealsdk.hooks import Type, add_hook, remove_hook

OUT = Path(sys.modules["helios_tracker"].__file__).resolve().parents[1] / "tools" / "probe_child_skill.txt"  # the repo, through the mod's junction
SAMPLE_FOR, SAMPLE_EVERY = 60.0, 0.25
SKIP = {"Outer", "Class", "ObjectArchetype", "ObjectFlags", "HashNext", "HashOuterNext", "StateFrame", "LinkerIndex",
        "ObjectInternalInteger", "NetIndex", "VfTableObject", "Linker", "Name"}
lines: list[str] = []


def _try(fn, default="<err>"):  # noqa: ANN001, ANN202
    try:
        return fn()
    except Exception as ex:  # noqa: BLE001
        return f"<{type(ex).__name__}>" if default == "<err>" else default


def _brief(value, depth: int = 0) -> str:  # noqa: ANN001
    if value is None:
        return "None"
    if isinstance(value, Enum):
        return str(value.name)
    if isinstance(value, (str, int, float, bool)):
        return f"{value:.2f}" if isinstance(value, float) else str(value)
    if depth > 2:
        return "..."
    if hasattr(value, "_type"):
        return "{" + ", ".join(f"{f.Name}={_brief(_try(lambda f=f: value._get_field(f)), depth + 1)}"
                               for f in _try(lambda: list(value._type._fields()), [])
                               if f.Class.Name.endswith("Property")) + "}"
    if hasattr(value, "_path_name") and hasattr(value, "Class"):
        return _try(lambda: value._path_name())
    if hasattr(value, "__len__"):
        return f"[{len(value)}: " + ", ".join(_brief(v, depth + 1) for v in list(value)[:8]) + "]"
    return str(value)


def _dump(title: str, obj) -> None:  # noqa: ANN001
    lines.append(f"   -- {title}: {_brief(obj)}")
    fields = _try(lambda: list(obj.Class._fields()), None)
    if fields is None:  # a struct
        fields = _try(lambda: list(obj._type._fields()), [])
    for f in fields:
        name = str(f.Name)
        if not f.Class.Name.endswith("Property") or name in SKIP:
            continue
        text = _brief(_try(lambda f=f: obj._get_field(f)))
        if text in ("0", "0.00", "False", "None", "[0: ]", "{}", ""):
            continue
        lines.append(f"      {name:36s} {text[:400]}")


def _tree_skills() -> dict[int, str]:
    """Skill definition address -> the tree skill naming it (anyone's tree)."""
    out = {}
    for pc in _try(lambda: list(unrealsdk.find_all("WillowPlayerController", exact=False)), []):
        tree = _try(lambda p=pc: p.PlayerSkillTree, None)
        for s in _try(lambda t=tree: list(t.Skills), []) or []:
            d = _try(lambda s=s: s.Definition, None)
            if d is not None:
                out[d._get_address()] = f"{_try(lambda: pc.PlayerReplicationInfo.PlayerName)}: {d.Name}"
    return out


def main() -> None:
    lines.append(f"probe_child_skill {time.strftime('%H:%M:%S')} - each active skill definition once")
    OUT.write_text("\n".join(lines), encoding="utf-8")
    manager = get_pc().GetSkillManager()
    tree = _tree_skills()
    hook_func, hook_id = "WillowGame.WillowGameViewportClient:PostRender", "helios_probe_child_skill"
    remove_hook(hook_func, Type.POST, hook_id)
    t0, state, seen = time.monotonic(), {"next": 0.0}, set()

    def tick(obj, args, ret, func):  # noqa: ANN001, ANN202, ARG001
        now = time.monotonic()
        if now - t0 > SAMPLE_FOR:
            remove_hook(hook_func, Type.POST, hook_id)
            lines.append(f"== done: {len(seen)} definitions")
            OUT.write_text("\n".join(lines), encoding="utf-8")
            print(f"[probe_child_skill] done -> {OUT}")
            return
        if now < state["next"]:
            return
        state["next"] = now + SAMPLE_EVERY
        for skill in _try(lambda: list(manager.ActiveSkills), []) or []:
            d = _try(lambda s=skill: s.Definition, None)
            key = _try(lambda: d._get_address(), None)
            if d is None or key in seen:
                continue
            seen.add(key)
            lines.append(f"== {now - t0:5.1f}s  {d.Name} '{_try(lambda: d.SkillName)}'"
                         f" in a tree: {tree.get(key, 'no')}  instigator={_brief(_try(lambda s=skill: s.SkillInstigator, None))}")
            _dump("Skill instance", skill)
            _dump("definition", d)
            OUT.write_text("\n".join(lines), encoding="utf-8")

    add_hook(hook_func, Type.POST, hook_id, tick)
    print(f"[probe_child_skill] sampling for {SAMPLE_FOR:.0f}s - trigger Blood Overdrive (or any timed passive)")


try:
    main()
except Exception as ex:  # noqa: BLE001
    lines.append(f"probe failed: {type(ex).__name__}: {ex}")
    OUT.write_text("\n".join(lines), encoding="utf-8")
