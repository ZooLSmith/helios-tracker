# Dev probe (in game), instant: what the page needs for the Pre-Sequel's own words and its Oz meter (.agent/presequel.md).
# 1. the game's localized texts, through the engine's Localize(Section, Key, Package) (Core.Object's, static - called on
#    Object's default object, each line written before its call): [CategoryLabels] - the inventory's category names
#    (the Pre-Sequel's Artifact "OZ KITS", BL2's "RELICS"; weapons, shields...) - and [Training] EridiumTitle (the
#    Pre-Sequel's "Moonstones"), from WillowGame.int in the game's language. Only these exact keys.
# 2. the Oz meter: WillowPawn.OxygenPool and WillowPlayerReplicationInfo.OxygenPool (the Pre-Sequel's; a pool
#    reference {PoolManager, PoolIndexInManager, PoolGUID, Data}, like SkillCooldownPool), their Data's CurrentValue,
#    MaxValue, MaxValueBaseValue, ConsumptionRate, OnIdleRegenerationRate / Delay, the pool's class. Properties only.
#    Note the HUD's O2 reading alongside (and whether you're in a vacuum or in air).
# Writes tools/probes/probe_tps2.txt (overwrites), after each line.
#   py exec(open(r"<repo>\tools\probes\probe_tps2.py").read())
import sys
from pathlib import Path

import unrealsdk
from mods_base import get_pc

OUT = Path(sys.modules["helios_tracker"].__file__).resolve().parents[1] / "tools" / "probes" / "probe_tps2.txt"  # the repo, through the mod's junction
CATEGORIES = ("Weapon", "Shield", "Grenade", "mod", "comm", "Artifact", "OzKit", "Items", "missionobject", "Health",
              "Ammo", "Customization_Skin", "Equipped", "Personal", "SDU")
lines: list[str] = []


def _flush() -> None:
    OUT.write_text("\n".join(lines), encoding="utf-8")


def _try(fn, default="<err>"):  # noqa: ANN001, ANN202
    try:
        return fn()
    except Exception as ex:  # noqa: BLE001
        return f"<{type(ex).__name__}: {ex}>" if default == "<err>" else default


def _step(label: str, fn) -> None:  # noqa: ANN001
    lines.append(f"   {label} ...")
    _flush()
    lines[-1] = f"   {label} = {_try(fn)!r}"
    _flush()


def _pool(label: str, ref) -> None:  # noqa: ANN001
    lines.append(f"-- {label}")
    if ref is None or isinstance(ref, str):
        lines.append(f"   {ref!r}")
        return
    data = _try(lambda: ref.Data, None)
    lines.append(f"   PoolIndexInManager={_try(lambda: ref.PoolIndexInManager)!r} PoolGUID={_try(lambda: ref.PoolGUID)!r}"
                 f" Data={_try(lambda: data._path_name()) if data is not None else None}"
                 f" ({_try(lambda: data.Class.Name) if data is not None else ''})")
    if data is not None and not isinstance(data, str):
        for name in ("CurrentValue", "MaxValue", "MaxValueBaseValue", "ConsumptionRate", "OnIdleRegenerationRate",
                     "OnIdleRegenerationDelay", "PassiveRegenerationRate", "ActiveRegenerationRate", "IsRegenerating"):
            lines.append(f"   {name} = {_try(lambda n=name: getattr(data, n))!r}")
    _flush()


def main() -> None:
    lines.append("== 1. Localize")
    _flush()
    cdo = _try(lambda: unrealsdk.find_class("Object").ClassDefaultObject, None)
    lines.append(f"   Object's default object: {cdo!r}"[:200])
    if cdo is not None and not isinstance(cdo, str):
        for key in CATEGORIES:
            _step(f"Localize('CategoryLabels', {key!r}, 'WillowGame')", lambda k=key: cdo.Localize("CategoryLabels", k, "WillowGame"))
        _step("Localize('Training', 'EridiumTitle', 'WillowGame')", lambda: cdo.Localize("Training", "EridiumTitle", "WillowGame"))
    lines.append("== 2. the Oz meter")
    _flush()
    pc = get_pc()
    pawn = _try(lambda: pc.Pawn, None)
    _pool("pawn.OxygenPool", _try(lambda: pawn.OxygenPool) if pawn is not None else None)
    _pool("pc.PlayerReplicationInfo.OxygenPool", _try(lambda: pc.PlayerReplicationInfo.OxygenPool))
    lines.append("done")
    _flush()


main()
print(f"probe_tps2: written to {OUT}")
