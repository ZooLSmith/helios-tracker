# Dev probe (in game), samples for 90 s, read-only: what the other players' replicated action skill
# timers mean on a co-op client. probe_coop found NextActionSkillActiveAbilityTime /
# NextActionSkillCooldownAbilityTime on their pawn (148.9 both, 0 on ours) - world times, but of what?
# Logs them with the world time (and ours, from our controller, for comparison) whenever they change.
# Run it joined to someone else's game, then ask them to use their action skill (and wait out the cooldown).
# Writes E:\Projects\python\bl2-helios-tracker\tools\probe_coop_skill.txt (overwrites)
#   py exec(open(r"E:\Projects\python\bl2-helios-tracker\tools\probe_coop_skill.py").read())
import time
from pathlib import Path

from mods_base import ENGINE, get_pc
from unrealsdk.hooks import Type, add_hook, remove_hook

OUT = Path(r"E:\Projects\python\bl2-helios-tracker\tools\probe_coop_skill.txt")
SAMPLE_FOR, SAMPLE_EVERY = 90.0, 0.25
FIELDS = ("NextActionSkillActiveAbilityTime", "NextActionSkillCooldownAbilityTime")
lines: list[str] = []


def _try(fn, default="<err>"):  # noqa: ANN001, ANN202
    try:
        return fn()
    except Exception as ex:  # noqa: BLE001
        return f"<{type(ex).__name__}>" if default == "<err>" else default


def _fmt(v) -> str:  # noqa: ANN001
    return f"{v:.2f}" if isinstance(v, float) else str(v)


def _sample() -> str:
    wi = ENGINE.GetCurrentWorldInfo()
    pc = get_pc()
    me = _try(lambda: pc.Pawn, None)
    parts = []
    p = wi.PawnList
    while p is not None:
        if "PlayerPawn" in str(p.Class.Name):
            who = "me" if p == me else str(_try(lambda q=p: q.PlayerReplicationInfo.PlayerName, "?"))
            vals = " ".join(f"{f[len('NextActionSkill'):]}={_fmt(_try(lambda q=p, f=f: getattr(q, f)))}" for f in FIELDS)
            parts.append(f"{who}: {vals}")
        p = _try(lambda q=p: q.NextPawn, None)
    ours = _try(lambda: pc.SkillCooldownPool.Data.CurrentValue, None)  # our cooldown left, for comparison
    parts.append(f"our cooldown pool={_fmt(ours)}")
    return " | ".join(parts)


def main() -> None:
    lines.append(f"probe_coop_skill {time.strftime('%H:%M:%S')} - samples (changes only), world time first")
    OUT.write_text("\n".join(lines), encoding="utf-8")
    hook_func, hook_id = "WillowGame.WillowGameViewportClient:PostRender", "helios_probe_coop_skill"
    remove_hook(hook_func, Type.POST, hook_id)
    t0, state = time.monotonic(), {"next": 0.0, "last": ""}

    def tick(obj, args, ret, func):  # noqa: ANN001, ANN202, ARG001
        now = time.monotonic()
        if now - t0 > SAMPLE_FOR:
            remove_hook(hook_func, Type.POST, hook_id)
            lines.append("== done")
            OUT.write_text("\n".join(lines), encoding="utf-8")
            print(f"[probe_coop_skill] done, {len(lines)} lines -> {OUT}")
            return
        if now < state["next"]:
            return
        state["next"] = now + SAMPLE_EVERY
        sample = _try(_sample)
        if sample != state["last"]:
            state["last"] = sample
            world = _try(lambda: float(ENGINE.GetCurrentWorldInfo().TimeSeconds), 0.0)
            lines.append(f"  t={world:8.2f}  {sample}")
            OUT.write_text("\n".join(lines), encoding="utf-8")

    add_hook(hook_func, Type.POST, hook_id, tick)
    print(f"[probe_coop_skill] sampling for {SAMPLE_FOR:.0f}s - have your friend use their action skill")


try:
    main()
except Exception as ex:  # noqa: BLE001
    lines.append(f"probe failed: {type(ex).__name__}: {ex}")
    OUT.write_text("\n".join(lines), encoding="utf-8")
