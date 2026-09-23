# Dev probe (in game), instant: the world scale (units per metre) from the player's size - the
# collision cylinder, eye height, mesh bounds. A human-sized character is ~1.8 m tall.
# Writes E:\Projects\python\borderlands-2\tools\probe_scale.txt (appends)
#   py exec(open(r"E:\Projects\python\borderlands-2\tools\probe_scale.py").read())
from pathlib import Path

from mods_base import get_pc

OUT = Path(r"E:\Projects\python\borderlands-2\tools\probe_scale.txt")


def _try(fn):  # noqa: ANN001, ANN202
    try:
        return fn()
    except Exception as ex:  # noqa: BLE001
        return f"<{type(ex).__name__}: {ex}>"


pc = get_pc()
pawn = _try(lambda: pc.MyWillowPawn) or pc.Pawn
lines = [
    "#" * 60,
    f"pawn {pawn.Class.Name} {pawn.Name}",
    f"  CylinderComponent.CollisionHeight (half height) = {_try(lambda: pawn.CylinderComponent.CollisionHeight)}",
    f"  CylinderComponent.CollisionRadius = {_try(lambda: pawn.CylinderComponent.CollisionRadius)}",
    f"  BaseEyeHeight = {_try(lambda: pawn.BaseEyeHeight)}  EyeHeight = {_try(lambda: pawn.EyeHeight)}",
    f"  Mesh.Bounds = {_try(lambda: pawn.Mesh.Bounds)}",
    f"  DrawScale = {_try(lambda: pawn.DrawScale)}  Mesh.Scale = {_try(lambda: pawn.Mesh.Scale)}",
    f"  GroundSpeed (run speed, uu/s) = {_try(lambda: pawn.GroundSpeed)}",
    f"  JumpZ = {_try(lambda: pawn.JumpZ)}",
]
height = _try(lambda: 2 * float(pawn.CylinderComponent.CollisionHeight))
if isinstance(height, float) and height > 0:
    lines.append(f"  => collision height {height:.0f} uu: {height / 1.8:.0f} uu per metre if the character is 1.8 m tall")
with OUT.open("a", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")
print("\n".join(lines))
