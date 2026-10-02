# Dev probe (in game), instant: the game's own item serial for the held weapon and the first backpack
# items - WillowInventory.CreateSerialNumber() (an InventorySerialNumber struct) and GetSerialNumberString(),
# both native, no parameters, called on real inventory only (tools/probes/probe_serial.txt found them) - and the
# Gibbed code built from the serial's bytes (BL2(...) / BLOZ(...), unique id cleared the way Gibbed copies).
# Hold a weapon when running it.
# Writes tools/probes/probe_serial2.txt (rewritten after each item)
#   py exec(open(r"<repo>\tools\probes\probe_serial2.py").read())
import base64
import sys
import zlib
from pathlib import Path

from mods_base import get_pc

OUT = Path(sys.modules["helios_tracker"].__file__).resolve().parents[1] / "tools" / "probes" / "probe_serial2.txt"  # the repo, through the mod's junction
BACKPACK = 3  # backpack items tried after the held weapon

lines: list[str] = []


def _save() -> None:
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _try(fn, default="<err>"):  # noqa: ANN001, ANN202
    try:
        return fn()
    except Exception as ex:  # noqa: BLE001
        return f"<{type(ex).__name__}: {ex}>" if default == "<err>" else default


def _bogo(seed: int, buf: bytes, encrypt: bool) -> bytes:
    """Gibbed's BogoEncrypt / BogoDecrypt (PackedDataHelper.cs) over the bytes after the 5-byte header."""
    if seed == 0 or not buf:
        return buf
    n = len(buf)
    right = (seed % 32) % n
    if encrypt:
        buf = buf[right:] + buf[:right]
    xor = ((seed - (1 << 32) if seed >= 1 << 31 else seed) >> 5) & 0xFFFFFFFF
    out = bytearray(buf)
    for i in range(n):
        xor = (xor * 0x10A860C1) % 0xFFFFFFFB
        out[i] ^= xor & 0xFF
    return bytes(out) if encrypt else bytes(out[n - right:] + out[:n - right])


def _check(plain: bytes) -> int:
    padded = bytearray(plain[:5] + b"\xff\xff" + plain[7:])
    padded += b"\xff" * (40 - len(padded))
    h = zlib.crc32(bytes(padded))
    return ((h >> 16) ^ h) & 0xFFFF


def _gibbed(data: bytes, prefix: str) -> str:
    """The serial as Gibbed copies it: decrypted, unique id 0 (then no scrambling), check recomputed."""
    seed = int.from_bytes(data[1:5], "big")
    plain = bytearray(data[:5] + _bogo(seed, data[5:], False))
    lines.append(f"      check in serial ok: {int.from_bytes(plain[5:7], 'big') == _check(bytes(plain))}")
    plain[1:5] = b"\0\0\0\0"
    plain[5:7] = _check(bytes(plain)).to_bytes(2, "big")
    return f"{prefix}({base64.b64encode(bytes(plain)).decode()})"


def _bytes(value) -> bytes | None:  # noqa: ANN001
    try:
        return bytes(int(b) & 0xFF for b in value)
    except TypeError:
        return None


def _one(inv, label: str, prefix: str) -> None:  # noqa: ANN001
    lines.append(f"== {label}: {_try(inv._path_name)}  ({_try(lambda: str(inv.DefinitionData.BalanceDefinition._path_name()))})")
    lines.append(f"   UniqueId = {_try(lambda: int(inv.DefinitionData.UniqueId))}")
    lines.append(f"   GetSerialNumberString() = {_try(lambda: repr(inv.GetSerialNumberString()))}")
    _save()
    result = _try(lambda: inv.CreateSerialNumber())
    lines.append(f"   CreateSerialNumber() -> {type(result).__name__}: {result!r}"[:600])
    _save()
    for n, serial in enumerate(result if isinstance(result, tuple) else (result,)):
        if not hasattr(serial, "_type"):
            continue
        buf = _try(lambda s=serial: s.Buffer)
        lines.append(f"   [{n}] Buffer ({type(buf).__name__}) = {buf!r}"[:600])
        for field in ("State", "RunningCounter", "EncryptedLength"):
            lines.append(f"   [{n}] {field} = {_try(lambda s=serial, f=field: getattr(s, f))}")
        data = _bytes(buf)
        if data is None:
            continue
        length = _try(lambda s=serial: int(s.EncryptedLength), 0)
        lines.append(f"   [{n}] bytes ({len(data)}): {data.hex()}")
        for cut, part in (("EncryptedLength", data[:length] if 5 <= length <= 40 else None), ("trailing 0xFF / 0 trimmed", data.rstrip(b"\xff").rstrip(b"\0"))):
            if part:
                lines.append(f"   [{n}] Gibbed code (bytes cut at {cut}, {len(part)}): {_try(lambda p=part: _gibbed(p, prefix))}")
        _save()


def main() -> None:
    pc = get_pc()
    engine = _try(lambda: pc.WorldInfo.Game.Class._path_name(), "")
    prefix = "BLOZ" if "Oz" in engine or "Oz" in _try(lambda: pc.Class._path_name(), "") else "BL2"
    lines.append(f"game class: {engine}  -> prefix {prefix} (check it)")
    weapon = _try(lambda: pc.Pawn.Weapon, None)
    if weapon is not None and not isinstance(weapon, str):
        _one(weapon, "held weapon", prefix)
    backpack = _try(lambda: list(pc.Pawn.InvManager.Backpack), []) or []
    for n, inv in enumerate(backpack[:BACKPACK]):
        _one(inv, f"backpack {n}", prefix)


try:
    main()
except Exception as ex:  # noqa: BLE001
    lines.append(f"probe failed: {type(ex).__name__}: {ex}")
_save()
