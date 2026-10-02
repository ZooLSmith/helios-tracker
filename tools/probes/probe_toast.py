# Dev probe (in game), instant: the game's own on-screen messages - the bottom-left one (co-op joins, connection
# lost: the OnlineMessage movie, ui_utils.show_coop_message -> pc.GetOnlineMessageMovie().DisplayMessage) and the HUD
# movie's (training text, challenge / badass token popups) - looking for one that takes an icon, or a clip of
# that container to fill with our own text / image (an in-game toast for the updater).
# Reads only: properties, the classes' function signatures, the movies' SwfMovie (to extract offline next). Calls
# only the two getters ui_utils already uses (GetOnlineMessageMovie, GetHUDMovie) and find_all("Class") once.
# Writes tools/probes/probe_toast.txt (overwrites), after each section.
#   py exec(open(r"<repo>\tools\probes\probe_toast.py").read())
import re
import sys
from pathlib import Path

import unrealsdk
from mods_base import get_pc


def _repo_tools() -> Path:
    """tools/probes in the repo: through the mod's junction, or the parked one (the .sdkmod running)."""
    here = Path(sys.modules["helios_tracker"].__file__).resolve().parents[1]
    if (here / "tools").is_dir():
        return here / "tools" / "probes"
    sdk_mods = next(p for p in Path(sys.modules["helios_tracker"].__file__).parents if p.name == "sdk_mods")
    return (sdk_mods / ".helios_tracker_dev").resolve().parent / "tools" / "probes"


OUT = _repo_tools() / "probe_toast.txt"
INTERESTING = re.compile(r"message|display|show|hide|notif|toast|popup|train|challenge|token|discover|icon|image|"
                         r"reward|online|coop|join|text|clip|invoke|variable|tooltip|queue", re.I)
CPF_PARM, CPF_OUT, CPF_RETURN = 0x80, 0x100, 0x400
lines: list[str] = []


def out(text: str = "") -> None:
    lines.append(text)


def flush() -> None:
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _try(fn, default="<err>"):  # noqa: ANN001, ANN202
    try:
        return fn()
    except Exception as ex:  # noqa: BLE001
        return f"<{type(ex).__name__}: {ex}>" if default == "<err>" else default


def _brief(value) -> str:  # noqa: ANN001
    if value is None:
        return "None"
    if hasattr(value, "_path_name") and hasattr(value, "Class"):
        return f"{value.Class.Name}'{_try(lambda: value._path_name())}'"
    text = repr(value)
    return text if len(text) < 200 else text[:200] + "..."


def _type(prop) -> str:  # noqa: ANN001
    kind = str(prop.Class.Name).removesuffix("Property")
    if kind == "Object" and (cls := _try(lambda: prop.PropertyClass, None)) is not None:
        return str(cls.Name)
    if kind == "Struct" and (st := _try(lambda: prop.Struct, None)) is not None:
        return str(st.Name)
    return kind


def _signature(func) -> str:  # noqa: ANN001
    params, ret = [], ""
    for p in _try(lambda: list(func._fields()), []):
        flags = int(_try(lambda p=p: p.PropertyFlags, 0) or 0)
        if flags & CPF_RETURN:
            ret = f" -> {_type(p)}"
        elif flags & CPF_PARM:
            params.append(f"{'out ' if flags & CPF_OUT else ''}{_type(p)} {p.Name}")
    return f"{func.Name}({', '.join(params)}){ret}"


def dump_object(label: str, obj, every: bool) -> None:  # noqa: ANN001
    """obj's class chain: each class's properties (with values) and functions (signatures); `every`: all of them,
    else the INTERESTING names."""
    out(f"==== {label}: {_brief(obj)}")
    if obj is None or isinstance(obj, str):
        flush()
        return
    cls = obj.Class
    while cls is not None and cls.Name != "Object":
        props, funcs = [], []
        for f in _try(lambda cls=cls: list(cls._fields()), []):
            kind = str(f.Class.Name)
            if not (every or INTERESTING.search(str(f.Name))):
                continue
            if kind == "Function":
                funcs.append(f"    {_signature(f)}")
            elif kind.endswith("Property"):
                props.append(f"    {_type(f)} {f.Name} = {_try(lambda f=f: _brief(obj._get_field(f)))}")
        if props or funcs:
            out(f"  -- {cls.Name}")
            out("\n".join(props + funcs))
        cls = cls.SuperField
    out()
    flush()


pc = get_pc()
online = _try(lambda: pc.GetOnlineMessageMovie(), None)
hud = _try(lambda: pc.GetHUDMovie(), None)

out("# the movies' SwfMovie (MovieInfo): extract offline to see their clips")
for name, movie in (("online message", online), ("hud", hud)):
    out(f"{name}: {_brief(movie)} MovieInfo={_try(lambda movie=movie: _brief(movie.MovieInfo))}")
out()
flush()

dump_object("OnlineMessage movie (every property / function)", online, every=True)
dump_object("HUD movie (interesting names)", hud, every=False)

out("==== GFx movie classes (names: message / notif / toast / popup / challenge / training / reward / token)")
for cls in _try(lambda: list(unrealsdk.find_all("Class", exact=False)), []):
    name = str(cls.Name)
    if re.search(r"message|notif|toast|popup|challenge|training|reward|token", name, re.I):
        chain, c = [], cls.SuperField
        while c is not None and len(chain) < 6:
            chain.append(str(c.Name))
            c = c.SuperField
        if any("GFx" in n for n in [name, *chain]):
            out(f"  {name} <- {' <- '.join(chain)}")
flush()
print(f"probe_toast: {OUT}")
