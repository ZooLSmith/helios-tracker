# Dev probe (in game), at once: how a pickup's amount is worked out (probe_pickup_amounts.txt: MonetaryValue 0 on cash;
# cash gives CreditsOnHand + the attribute AttrSlotValue_BaseCredits, ammo its pool + the InitializationDefinition
# Init_AmmoAmountShared_<type>). For one pickup per kind: its definition's ExternalAttributeEffects' base values
# unfolded - an InitializationDefinition's ValueFormula (Multiplier, Level, Power, Offset: each an
# AttributeInitializationData, unfolded in turn), its ConditionalInitialization / RandomVariance; an attribute's class,
# its ValueResolverChain (each resolver's class and properties) - and the item definition's / balance's attribute slots
# (AttributeSlotEffects, AttributeSlotUpgrades...: what fills AttrSlotValue_BaseCredits). Property reads only (no game
# calls). Stand near cash, eridium, ammo and health drops.
# Writes tools/probe_pickup_amounts2.txt (overwrites; after each pickup)
#   py exec(open(r"<repo>\tools\probe_pickup_amounts2.py").read())
import sys
from pathlib import Path

MOD = sys.modules["helios_tracker"]
OUT = Path(MOD.__file__).resolve().parents[1] / "tools" / "probe_pickup_amounts2.txt"
MAX_DEPTH = 5
col = MOD._collector  # noqa: SLF001
util = MOD.util
lines: list[str] = []


def _write() -> None:
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _get(obj, name):  # noqa: ANN001, ANN202
    try:
        return getattr(obj, name)
    except Exception as ex:  # noqa: BLE001
        return f"<{type(ex).__name__}>"


def _name(o) -> str:  # noqa: ANN001
    if o is None or isinstance(o, str):
        return str(o)
    return f"{_get(o, 'Name')} [{_get(_get(o, 'Class'), 'Name')}]"


def _props(obj) -> list[tuple[str, object]]:  # noqa: ANN001
    """Its properties (name, value), by the class's own list - reads only, the plain ones and object names."""
    out = []
    try:
        props = list(obj.Class._fields())
    except Exception:  # noqa: BLE001
        return out
    for prop in props:
        kind = str(_get(_get(prop, "Class"), "Name"))
        if not kind.endswith("Property") or kind in ("DelegateProperty",):
            continue
        name = str(_get(prop, "Name"))
        if name in NOISE:
            continue
        out.append((name, _get(obj, name)))
    return out


NOISE = {"VfTableObject", "HashNext", "ObjectFlags", "HashOuterNext", "StateFrame", "Linker", "LinkerIndex",
         "ObjectInternalInteger", "NetIndex", "Outer", "Name", "Class", "ObjectArchetype"}


def _cond(cond, pad: str, depth: int) -> None:  # noqa: ANN001
    """A conditional (ValueExpressions / ConditionalInitialization): each case's expressions, its value; the default."""
    for n, case in enumerate(_get(cond, "ConditionalExpressionList") or []):
        lines.append(f"{pad}case {n}:")
        for e in _get(case, "Expressions") or []:
            op2 = _get(e, "AttributeOperand2")
            lines.append(f"{pad}  if {_name(_get(e, 'AttributeOperand1'))} {getattr(_get(e, 'ComparisonOperator'), 'name', '?')} "
                         f"{_name(op2) if op2 is not None else ''} {getattr(_get(e, 'Operand2Usage'), 'name', '?')} "
                         f"const {_get(e, 'ConstantOperand2')}")
            for attr in (_get(e, "AttributeOperand1"), op2):
                if attr is not None and not isinstance(attr, str) and depth < MAX_DEPTH:
                    _attr(attr, pad + "    ", depth + 1)
        lines.append(f"{pad}  then:")
        _data(_get(case, "BaseValueIfTrue"), pad + "    ", depth + 1)
    lines.append(f"{pad}default:")
    _data(_get(cond, "DefaultBaseValue"), pad + "  ", depth + 1)


def _data(data, pad: str, depth: int) -> None:  # noqa: ANN001
    """An AttributeInitializationData, unfolded."""
    if depth > MAX_DEPTH:
        lines.append(pad + "...")
        return
    init, attr = _get(data, "InitializationDefinition"), _get(data, "BaseValueAttribute")
    lines.append(f"{pad}const {_get(data, 'BaseValueConstant')} scale {_get(data, 'BaseValueScaleConstant')} "
                 f"attr {_name(attr)} init {_name(init)}")
    if init is not None and not isinstance(init, str):
        _init(init, pad + "  ", depth + 1)
    if attr is not None and not isinstance(attr, str):
        _attr(attr, pad + "  ", depth + 1)


def _init(init, pad: str, depth: int) -> None:  # noqa: ANN001
    formula = _get(init, "ValueFormula")
    cond, rand = _get(init, "ConditionalInitialization"), _get(init, "RandomVariance")
    lines.append(f"{pad}formula enabled {_get(formula, 'bEnabled')}; conditional enabled {_get(cond, 'bEnabled')}; "
                 f"random enabled {_get(rand, 'bEnabled')}")
    for term in ("Multiplier", "Level", "Power", "Offset"):
        lines.append(f"{pad}{term}:")
        _data(_get(formula, term), pad + "  ", depth)
    if _get(cond, "bEnabled") is True:
        lines.append(f"{pad}conditional:")
        _cond(cond, pad + "  ", depth)
    if _get(rand, "bEnabled") is True:
        lines.append(f"{pad}random variance: {rand}")


def _attr(attr, pad: str, depth: int) -> None:  # noqa: ANN001
    lines.append(f"{pad}attribute {_name(attr)} path {_get(attr, '_path_name')() if callable(_get(attr, '_path_name')) else '?'}")
    for n, r in enumerate(_get(attr, "ValueResolverChain") or []):
        lines.append(f"{pad}  resolver {n}: {_name(r)}")
        for pname, value in _props(r):
            if pname == "ValueExpressions":
                lines.append(f"{pad}    ValueExpressions:")
                _cond(value, pad + "      ", depth)
                continue
            shown = _name(value) if hasattr(value, "Class") else value
            lines.append(f"{pad}    {pname} = {shown}")
    if str(_get(_get(attr, "Class"), "Name")) == "DesignerAttributeDefinition":
        lines.append(f"{pad}  base:")
        _data(_get(attr, "BaseValue"), pad + "    ", depth)


def _slots(owner, label: str) -> None:  # noqa: ANN001
    """An item definition's / balance's attribute slot lists (what fills AttrSlotValue_*)."""
    for pname, value in _props(owner):
        if "Slot" in pname or "Attribute" in pname:
            lines.append(f"  {label}.{pname} = {value if not hasattr(value, 'Class') else _name(value)}")


seen: set[str] = set()
for key, ptr in list(col._pickups.items()):  # noqa: SLF001
    p = ptr()
    if p is None:
        continue
    inv = _get(p, "Inventory")
    if inv is None or isinstance(inv, str):
        continue
    kind = util.pickup_kind(inv)
    if not kind or kind in seen:
        continue
    seen.add(kind)
    data = _get(inv, "DefinitionData")
    definition = _get(data, "ItemDefinition")
    lines.append(f"\n== {kind}: {_name(inv)} def {_name(definition)} balance {_name(_get(data, 'BalanceDefinition'))} "
                 f"ExpLevel {_get(inv, 'ExpLevel')} GameStage {_get(inv, 'GameStage')}")
    for n, effect in enumerate(_get(definition, "ExternalAttributeEffects") or []):
        lines.append(f"  effect {n}: {_name(_get(effect, 'AttributeToModify'))} {getattr(_get(effect, 'ModifierType'), 'name', '?')}")
        _data(_get(effect, "BaseModifierValue"), "    ", 0)
    _slots(definition, "definition")
    for n, slot in enumerate(_get(definition, "AttributeSlotEffects") or []):  # (cash: BaseCredits - its value unfolded)
        lines.append(f"  slot effect {n} {_get(slot, 'SlotName')} -> {_name(_get(slot, 'AttributeToModify'))} value:")
        _data(_get(slot, "BaseModifierValue"), "    ", 0)
        lines.append("    per grade:")
        _data(_get(slot, "PerGradeUpgrade"), "      ", 0)
    lines.append(f"  item: MonetaryValueModifierTotal {_get(inv, 'MonetaryValueModifierTotal')} "
                 f"balance grades {_get(_get(data, 'BalanceDefinition'), 'Grades') if hasattr(_get(data, 'BalanceDefinition'), 'Class') else '-'}")
    _write()
_write()
print(f"probe_pickup_amounts2: written {OUT} ({sorted(seen)})")
