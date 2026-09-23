"""
The mission log (game thread): every mission of the playthrough with its status, objectives and
progress, and what it depends on - for the page's quest panel and mission tree.

Verified in game (tools/probe_quests.py): MissionTracker.MissionList[] = {MissionDef, Status
(EMissionStatus: MS_NotStarted / MS_Active / MS_Complete seen), ObjectivesProgress[] (one count per
MissionDef.ObjectiveDefs entry, same order; empty before the mission starts), ActiveObjectiveSet
(a MissionObjectiveSetDefinition: its ObjectiveDefinitions are the current step), SubObjectiveSets}.

Definitions never change: each is read once (cached forever, by address). The live part (status,
progress, current step) is read by a full pass over the list (every few seconds) and a fast pass
over the tracked / active missions only (every second).

Rewards (tools/probe_rewards.py): MissionDefinition.GetExperienceReward(pc, bAlt) /
GetCurrencyReward(pc, bAlt) / GetCurrencyRewardType(bAlt) - what the game's mission screen shows,
scaled to the player; items: Reward.RewardItems (balance definitions) / RewardItemPools. Function
calls: only for the active / available / tracked missions, cached per (mission, player level).
"""

from typing import Any

from .util import def_name, named, try_

# MissionDefinition (address) -> (its record for the page, {objective address: index})
_defs: dict[int, tuple[dict[str, Any], dict[int, int]]] = {}
# (MissionDefinition address, player level) -> reward (see _reward)
_rewards: dict[tuple[int, int], dict[str, Any]] = {}


def mission_id(mdef: Any) -> str:
    """A mission's id on the page: its definition's path name (unique, stable across levels)."""
    return try_(lambda: str(mdef._path_name()), "") or def_name(mdef)


def _text(obj: Any, prop: str) -> str:
    return try_(lambda: str(getattr(obj, prop)), "") or ""


def _definition(mdef: Any) -> tuple[dict[str, Any], dict[int, int]]:
    key = mdef._get_address()
    if (cached := _defs.get(key)) is not None:
        return cached
    objectives, index = [], {}
    for i, obj in enumerate(try_(lambda: list(mdef.ObjectiveDefs), []) or []):
        if obj is None:
            continue
        index[obj._get_address()] = i
        objectives.append({
            **named(_text(obj, "ProgressMessage"), def_name(obj)),
            "c": try_(lambda o=obj: int(o.ObjectiveCount), 1) or 1,
            **({"opt": 1} if try_(lambda o=obj: bool(o.bObjectiveIsOptional), False) else {}),
        })
    record = {
        "i": mission_id(mdef),
        **named(_text(mdef, "MissionName"), def_name(mdef)),
        "num": try_(lambda: int(mdef.MissionNumber), 0),
        "plot": 1 if try_(lambda: bool(mdef.bPlotCritical), False) else 0,
        "deps": [mission_id(d) for d in try_(lambda: list(mdef.Dependencies), []) or [] if d is not None],
        "desc": _text(mdef, "MissionDescription"),
        "summary": _text(mdef, "MissionSummary"),
        "giver": _text(mdef, "MissionGiver"),
        "turnin": _text(mdef, "MissionTurnInLocation"),
        "stage": try_(lambda: int(mdef.GameStage), 0),
        "obj": objectives,
    }
    # Its area: the travel station's name, as the game shows it (tools/probe_mission_areas.py:
    # TravelStation.StationDisplayName - "Three Horns Divide", "Claptrap's Place"...)
    if area := try_(lambda: str(mdef.TravelStation.StationDisplayName), ""):
        record["area"] = area
    if (nxt := try_(lambda: mdef.NextMissionInChain)) is not None:
        record["next"] = mission_id(nxt)
    if try_(lambda: bool(mdef.bRepeatable), False):
        record["repeat"] = 1
    if try_(lambda: bool(mdef.bCanBeFailed), False):
        record["fail"] = 1
    _defs[key] = (record, index)
    return record, index


def _reward_side(mdef: Any, pc: Any, alt: bool) -> dict[str, Any]:
    """One reward (normal / alternative): XP and currency for this player, item rewards."""
    out: dict[str, Any] = {}
    if (xp := try_(lambda: int(mdef.GetExperienceReward(pc, alt)), 0)) > 0:
        out["xp"] = xp
    if (money := try_(lambda: int(mdef.GetCurrencyReward(pc, alt)), 0)) > 0:
        out["cash"] = money
        currency = try_(lambda: mdef.GetCurrencyRewardType(alt))
        out["cur"] = str(getattr(currency, "name", currency) or "").removeprefix("CURRENCY_")
    reward = try_(lambda: mdef.AlternativeReward if alt else mdef.Reward)
    items = [named("", def_name(b)) for b in try_(lambda: list(reward.RewardItems), []) or [] if b is not None]
    pools = [named("", def_name(p)) for p in try_(lambda: list(reward.RewardItemPools), []) or [] if p is not None]
    if items:
        out["items"] = items  # balance definitions: made-up names (the game shows generated items)
    if pools:
        out["pools"] = pools
    return out


def _reward(mdef: Any, pc: Any, level: int) -> dict[str, Any]:
    """The mission's reward for this player (cached per player level): {xp, cash, cur, items, pools}
    plus "alt" (the alternative reward) when the mission has one."""
    key = (mdef._get_address(), level)
    if (cached := _rewards.get(key)) is None:
        cached = _reward_side(mdef, pc, False)
        if try_(lambda: bool(mdef.bEnableAltReward), False) and (alt := _reward_side(mdef, pc, True)):
            cached["alt"] = alt
        _rewards[key] = cached
    return cached


def _status_name(status: Any) -> str:
    """EMissionStatus.MS_Active -> "Active" (the game's own name; the page translates known ones)."""
    name = getattr(status, "name", None) or str(status)
    return str(name).removeprefix("MS_")


def _live(entry: Any, index: dict[int, int]) -> tuple[str, tuple[int, ...], tuple[int, ...], bool]:
    """(status, progress per objective, indices of the current step's objectives, offered): offered =
    bHeardKickoff - the giver offered it (its kickoff dialog; unverified in game): a mission not
    started yet that nobody offered is still to be found."""
    status = _status_name(try_(lambda: entry.Status, ""))
    progress = tuple(int(v) for v in try_(lambda: list(entry.ObjectivesProgress), []) or [])
    current = []
    sets = [try_(lambda: entry.ActiveObjectiveSet)] + list(try_(lambda: list(entry.SubObjectiveSets), []) or [])
    for s in sets:
        for obj in try_(lambda s=s: list(s.ObjectiveDefinitions), []) or []:
            if obj is not None and (i := index.get(obj._get_address())) is not None and i not in current:
                current.append(i)
    return status, progress, tuple(current), bool(try_(lambda: entry.bHeardKickoff, False))


class MissionLog:
    """The log's state between passes; `payload()` gives what the page gets."""

    def __init__(self) -> None:
        self._records: list[dict[str, Any]] = []  # per MissionList entry (the definition's record)
        self._mdefs: list[Any] = []  # the definitions (static game data)
        self._rewards: dict[int, dict[str, Any]] = {}  # entry -> reward (active / available / tracked)
        self._addrs: list[int] = []  # MissionDef address per entry (the fast pass checks the order)
        self._indexes: list[dict[int, int]] = []
        self._live: list[tuple[str, tuple[int, ...], tuple[int, ...], bool]] = []
        self._watch: list[int] = []  # entries the fast pass reads: active ones and the tracked one
        self._tracked = ""
        self.dirty = False  # changed since the last payload()

    def full(self, tracker: Any, pc: Any = None) -> None:
        """Every entry: definitions (cached) and live state; rewards of the ones that matter."""
        records, addrs, indexes, live, watch, mdefs = [], [], [], [], [], []
        for n, entry in enumerate(try_(lambda: list(tracker.MissionList), []) or []):
            mdef = try_(lambda e=entry: e.MissionDef)
            if mdef is None:
                continue
            record, index = _definition(mdef)
            state = _live(entry, index)
            records.append(record)
            mdefs.append(mdef)
            addrs.append((n, mdef._get_address()))
            indexes.append(index)
            live.append(state)
            if state[0] not in ("NotStarted", "Complete"):
                watch.append(len(records) - 1)
        if [a for _, a in addrs] != [a for _, a in self._addrs] or live != self._live:
            self.dirty = True
        self._records, self._addrs, self._indexes, self._live, self._watch = records, addrs, indexes, live, watch
        self._mdefs = mdefs
        self._track(tracker)
        self._update_rewards(pc)

    def _update_rewards(self, pc: Any) -> None:
        """Rewards of the active, available (every dependency done) and tracked missions."""
        if pc is None:
            return
        level = try_(lambda: int(pc.PlayerReplicationInfo.ExpLevel), 0)
        status = {r["i"]: s[0] for r, s in zip(self._records, self._live, strict=True)}
        rewards = {}
        for k, (record, (st, *_)) in enumerate(zip(self._records, self._live, strict=True)):
            wanted = st == "Active" or record["i"] == self._tracked or (
                st == "NotStarted" and all(status.get(d) == "Complete" for d in record["deps"]))
            if wanted and (reward := _reward(self._mdefs[k], pc, level)):
                rewards[k] = reward
        if rewards != self._rewards:
            self._rewards = rewards
            self.dirty = True

    def fast(self, tracker: Any) -> bool:
        """The watched entries (and the tracked mission) only. False: the list changed under us
        (or the tracked mission is new): run a full pass."""
        if not self._records:
            return False
        if not self._track(tracker):
            return False
        entries = try_(lambda: tracker.MissionList)
        if entries is None:
            return False
        for k in self._watch:
            n, address = self._addrs[k]
            entry = try_(lambda n=n: entries[n])
            mdef = try_(lambda e=entry: e.MissionDef)
            if mdef is None or mdef._get_address() != address:
                return False
            state = _live(entry, self._indexes[k])
            if state != self._live[k]:
                self._live[k] = state
                self.dirty = True
        return True

    def _track(self, tracker: Any) -> bool:
        """Reads the tracked mission; False if it isn't one of the watched entries yet."""
        active = try_(lambda: tracker.ActiveMission)
        tracked = mission_id(active) if active is not None else ""
        if tracked != self._tracked:
            self._tracked = tracked
            self.dirty = True
        if not tracked:
            return True
        address = active._get_address()
        for k, (_, a) in enumerate(self._addrs):
            if a == address:
                if k not in self._watch:
                    self._watch.append(k)
                return True
        return False

    def payload(self, level_id: int) -> dict[str, Any]:
        self.dirty = False
        missions = []
        for k, (record, (status, progress, current, offered)) in enumerate(zip(self._records, self._live, strict=True)):
            m = {**record, "st": status}
            if offered:
                m["kick"] = 1
            if (reward := self._rewards.get(k)) is not None:
                m["rw"] = reward
            if progress:
                m["p"] = list(progress)
            if current:
                m["cur"] = list(current)
            missions.append(m)
        return {"level": level_id, "tracked": self._tracked or None, "missions": missions}
