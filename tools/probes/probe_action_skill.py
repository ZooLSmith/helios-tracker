# Dev probe (in game, co-op HOST), 120 s: what the host sees of the OTHER players' action skill -
# the page shows "ready" for everyone. Run it, then have each player use their action skill (and you
# yours) and wait for the cooldowns to run out; say who used it when.
# Logs (changes only, sampled every 0.25 s; floats rounded to 0.1): per player - their controller's
# SkillCooldownPool (object + Data: CurrentValue, ConsumptionRate, MaxValue...), GetSkillCooldownTime(),
# SavedSkillTreeSkill, every float / int / bool / byte property on the controller, pawn and player info
# whose name looks action skill / cooldown related; the running action skill instances in the skill
# manager (by instigator); and once, the controllers' tree action skill.
# Writes tools/probes/probe_action_skill.txt (overwrites)
#   py exec(open(r"<repo>\tools\probes\probe_action_skill.py").read())
import enum
import re
import time
import sys
from pathlib import Path

from mods_base import ENGINE, get_pc
from unrealsdk.hooks import Type, add_hook, remove_hook

OUT = Path(sys.modules["helios_tracker"].__file__).resolve().parents[1] / "tools" / "probes" / "probe_action_skill.txt"  # the repo, through the mod's junction
SAMPLE_FOR = 120.0
SAMPLE_EVERY = 0.25
PATTERN = re.compile(r"action|cooldown|skill|ability", re.I)
SCALARS = {"FloatProperty", "IntProperty", "BoolProperty", "ByteProperty", "ObjectProperty"}
lines: list[str] = []
_class_fields: dict[str, list] = {}


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
    if isinstance(value, float):
        return f"{value:.1f}"
    if hasattr(value, "_path_name") and hasattr(value, "Class"):
        return f"{value.Class.Name}'{value.Name}'"
    if hasattr(value, "_type") and hasattr(value._type, "_fields"):  # a struct
        return "{" + ", ".join(f"{f.Name}={_try(lambda f=f: _brief(value._get_field(f)))}"
                               for f in _try(lambda: list(value._type._fields()), []) if f.Class.Name in SCALARS) + "}"
    return repr(value)


def _fields(obj) -> list:  # noqa: ANN001
    key = _try(lambda: obj.Class._path_name(), "?")
    if key not in _class_fields:
        out, c = [], obj.Class
        while c is not None and c.Name != "Object":
            out += [f for f in _try(lambda c=c: list(c._fields()), []) if f.Class.Name in SCALARS and PATTERN.search(str(f.Name))]
            c = c.SuperField
        _class_fields[key] = out
    return _class_fields[key]


def _values(obj, label: str) -> dict[str, str]:  # noqa: ANN001
    if obj is None or isinstance(obj, str):
        return {}
    return {f"{label}.{f.Name}": _try(lambda f=f: _brief(obj._get_field(f))) for f in _fields(obj)}


def _players() -> list:
    wi = ENGINE.GetCurrentWorldInfo()
    out, p = [], _try(lambda: wi.PawnList, None)
    for _ in range(1000):
        if p is None or isinstance(p, str):
            break
        if "Player" in str(p.Class.Name):
            out.append(p)
        p = _try(lambda p=p: p.NextPawn, None)
    return out


def _label(pawn) -> str:  # noqa: ANN001
    me = _try(lambda: get_pc().MyWillowPawn, None)
    return "me" if me is not None and pawn == me else _try(lambda: str(pawn.PlayerReplicationInfo.PlayerName), "?")


def _sample() -> dict[str, str]:
    vals: dict[str, str] = {}
    pc = get_pc(possibly_loading=True)
    if pc is None:
        return vals
    for pawn in _players():
        who = _label(pawn)
        ctrl = _try(lambda p=pawn: p.Controller, None)
        vals |= _values(pawn, f"{who}:pawn")
        vals |= _values(_try(lambda p=pawn: p.PlayerReplicationInfo, None), f"{who}:PRI")
        if ctrl is None or isinstance(ctrl, str):
            vals[f"{who}:controller"] = "None"
            continue
        vals |= _values(ctrl, f"{who}:PC")
        pool = _try(lambda c=ctrl: c.SkillCooldownPool, None)
        vals[f"{who}:SkillCooldownPool"] = _brief(pool)
        data = _try(lambda: pool.Data, None) if pool is not None and not isinstance(pool, str) else None
        vals[f"{who}:SkillCooldownPool.Data"] = (f"{_brief(data)} value={_try(lambda: _brief(data.CurrentValue))}"
                                                 f" rate={_try(lambda: _brief(data.ConsumptionRate))}") if data is not None and not isinstance(data, str) else "-"
        vals[f"{who}:GetSkillCooldownTime()"] = _try(lambda c=ctrl: _brief(c.GetSkillCooldownTime()))
        vals[f"{who}:SavedSkillTreeSkill"] = _try(lambda c=ctrl: _brief(c.SavedSkillTreeSkill))
    manager = _try(lambda: pc.GetSkillManager(), None)
    running = []
    for s in _try(lambda: list(manager.ActiveSkills), []) or []:
        kind = _try(lambda s=s: s.Definition.SkillType.name, "?")
        if kind == "SKILL_TYPE_Action":
            running.append(f"{_try(lambda s=s: str(s.Definition.SkillName))} by {_try(lambda s=s: _brief(s.SkillInstigator))}"
                           f" state={_try(lambda s=s: _brief(s.SkillState))} duration={_try(lambda s=s: _brief(s.Duration))}")
    vals["running action skills"] = "; ".join(sorted(running))
    return vals


def main() -> None:
    lines.append(f"probe_action_skill {time.strftime('%H:%M:%S')} netmode={_try(lambda: ENGINE.GetCurrentWorldInfo().NetMode)}")
    for pawn in _players():  # each controller's tree action skill (the name fix)
        ctrl = _try(lambda p=pawn: p.Controller, None)
        acts = [f"{_try(lambda s=s: str(s.Definition.SkillName))} ({_try(lambda s=s: _brief(s.Definition))})"
                for s in _try(lambda c=ctrl: list(c.PlayerSkillTree.Skills), []) or []
                if _try(lambda s=s: s.Definition.SkillType.name, "") == "SKILL_TYPE_Action"]
        lines.append(f"   {_label(pawn)}: tree action skill {acts}")
    first = _try(_sample, {})
    lines.append("== initial values")
    lines.extend(f"   {k} = {v}" for k, v in sorted(first.items()))
    lines.append("== changes")
    OUT.write_text("\n".join(lines), encoding="utf-8")

    hook_func, hook_id = "WillowGame.WillowGameViewportClient:PostRender", "helios_probe_action_skill"
    remove_hook(hook_func, Type.POST, hook_id)
    t0, state = time.monotonic(), {"next": 0.0, "last": first}

    def tick(obj, args, ret, func):  # noqa: ANN001, ANN202, ARG001
        now = time.monotonic()
        if now - t0 > SAMPLE_FOR:
            remove_hook(hook_func, Type.POST, hook_id)
            lines.append("== done")
            OUT.write_text("\n".join(lines), encoding="utf-8")
            print(f"[probe_action_skill] done, {len(lines)} lines -> {OUT}")
            return
        if now < state["next"]:
            return
        state["next"] = now + SAMPLE_EVERY
        vals, last = _try(_sample, {}), state["last"]
        changed = [f"{k}: {last.get(k)} -> {vals.get(k)}" for k in sorted(set(vals) | set(last)) if vals.get(k) != last.get(k)]
        state["last"] = vals
        if changed:
            lines.append(f"  {now - t0:6.2f}s")
            lines.extend(f"      {c}" for c in changed)
            OUT.write_text("\n".join(lines), encoding="utf-8")

    add_hook(hook_func, Type.POST, hook_id, tick)
    print(f"[probe_action_skill] sampling for {SAMPLE_FOR:.0f}s - everyone use their action skill")


try:
    main()
except Exception as ex:  # noqa: BLE001
    lines.append(f"probe failed: {type(ex).__name__}: {ex}")
    OUT.write_text("\n".join(lines), encoding="utf-8")
