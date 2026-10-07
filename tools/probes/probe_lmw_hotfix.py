# Dev probe (in game), instant: whether Loot Midget World's hotfixes took (its .blcm, exec'd: the level merges are plain
# "set" lines - probe_lmw_levels.py; the container swaps are hotfixes, through Transient.SparkServiceConfiguration_6's
# Keys / Values - a Tundra Express bandit weapon chest still had its own definition, not the midget trap's). Reads the
# hotfix configurations (how many keys, the mod's among them?) and the object grades it changes (their
# DefaultInteractiveObject now). Read-only (properties only).
# Writes probe_lmw_hotfix.txt in the mod's data folder (sdk_mods/.helios_tracker; overwrites; after each section)
#   py exec(open(r"<repo>\tools\probes\probe_lmw_hotfix.py").read())
import unrealsdk

from helios_tracker.paths import DATA

OUT = DATA / "probe_lmw_hotfix.txt"
GRADES = ("GD_Balance_Treasure.ChestGrades.ObjectGrade_BanditWeaponChest",
          "GD_Balance_Treasure.ChestGrades.ObjectGrade_TreasureChest",
          "GD_Balance_Treasure.LootableGrades.ObjectGrade_Bandit_Cooler",
          "GD_Balance_Treasure.LootableGrades.ObjectGrade_MetalCrate")
lines: list[str] = []


def _write() -> None:
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _try(fn, default="<err>"):  # noqa: ANN001, ANN202
    try:
        return fn()
    except Exception as ex:  # noqa: BLE001
        return f"<{type(ex).__name__}: {ex}>" if default == "<err>" else default


lines.append("== hotfix configurations (SparkServiceConfiguration)")
for conf in unrealsdk.find_all("SparkServiceConfiguration", exact=False):
    if conf.Name.startswith("Default__"):
        continue
    keys = _try(lambda conf=conf: [str(k) for k in conf.Keys], [])
    values = _try(lambda conf=conf: [str(v) for v in conf.Values], [])
    midget = [v for v in values if "MidgetBandit" in v or "MidgetHyperion" in v]
    lines.append(f"{conf._path_name()}: {len(keys)} keys, {len(values)} values, {len(midget)} with a midget trap"
                 f" (ServiceName {_try(lambda conf=conf: conf.ServiceName)})")
    lines.extend(f"  {v[:200]}" for v in midget[:3])
_write()

lines.append("\n== the object grades it changes: their DefaultInteractiveObject now")
for path in GRADES:
    grade = _try(lambda path=path: unrealsdk.find_object("Object", path), None)
    if grade is None or isinstance(grade, str):
        lines.append(f"{path}: not found")
        continue
    lines.append(f"{path}: {_try(lambda grade=grade: grade.DefaultInteractiveObject)}")
_write()
lines.append("\ndone")
_write()
