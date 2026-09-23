"""
The mission log (game thread): every mission of the playthrough with its status, objectives and
progress, and what it depends on - for the page's quest panel and mission tree.

Verified in game (tools/probe_quests.py): MissionTracker.MissionList[] = {MissionDef, Status
(EMissionStatus: MS_NotStarted / MS_Active / MS_RequiredObjectivesComplete / MS_ReadyToTurnIn /
MS_Complete - tools/probe_turnin.txt), ObjectivesProgress[] (one count per
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

import time
from typing import Any

from .util import def_name, field, named, try_

# MissionDefinition (address) -> (its record for the page, {objective address: index})
_defs: dict[int, tuple[dict[str, Any], dict[int, int]]] = {}
STEP_ENTRIES = 60  # at most this many entries per step of the full pass (~290 in all: a few ticks)
STEP_SECONDS = 0.002  # and at most this long: the first cycle reads every definition (a lot more per entry)
REWARDS_SECONDS = 0.003  # per cycle, computing rewards not cached yet (function calls; the rest next cycle)

# (MissionDefinition address, player level, mission level) -> reward (see _reward). The mission's level
# is part of the key: it's only set when the mission is picked up (GameStage), changing the reward
_rewards: dict[tuple[int, int, int], dict[str, Any]] = {}
# The game's difficulty thresholds (GlobalsDefinition.LevelDifference_*: mission level - player level),
# read once (tools/probe_mission_level.txt: Impossible 5, Hard 3, Tough 1, Normal -3)
_thresholds: dict[str, int] | None = None


def difficulty_thresholds() -> dict[str, int]:
    global _thresholds  # noqa: PLW0603
    if not _thresholds:  # again until read (the globals may not be loaded yet)
        import unrealsdk  # noqa: PLC0415 - game only (the offline check never gets here with real data)

        globals_def = try_(lambda: unrealsdk.find_object("GlobalsDefinition", "GD_Globals.General.Globals"))
        _thresholds = {k.lower(): v for k in ("Impossible", "Hard", "Tough", "Normal")
                       if isinstance(v := try_(lambda k=k: int(getattr(globals_def, "LevelDifference_" + k))), int)}
    return _thresholds or {}


def mission_id(mdef: Any) -> str:
    """A mission's id on the page: its definition's path name (unique, stable across levels)."""
    return try_(lambda: str(mdef._path_name()), "") or def_name(mdef)


def _text(obj: Any, prop: str) -> str:
    return try_(lambda: str(getattr(obj, prop)), "") or ""


# Travel station definition address -> {"a": its name as the game shows it, "map": its level's map}
_stations: dict[int, dict[str, str]] = {}


def station(s: Any) -> dict[str, str] | None:
    """A travel station definition as the page gets it (tools/probe_area.txt): StationDisplayName and
    StationLevelName (the map it's in, e.g. "Ice_P": compared with the current level) - static, cached."""
    if s is None:
        return None
    key = s._get_address()
    if (info := _stations.get(key)) is None:
        info = {"a": _text(s, "StationDisplayName"), "map": _text(s, "StationLevelName")}
        _stations[key] = info
    return info if info["a"] or info["map"] else None


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
    # Where it comes from - where its giver is (Name Game: Sanctuary); not where it's done: see _live)
    if (home := try_(lambda: station(mdef.TravelStation))) is not None:
        if home["a"]:
            record["area"] = home["a"]
        if home["map"]:
            record["map"] = home["map"]
    # Where to hand it in (TurnInStation; None: back at its own station)
    if (turn_in := try_(lambda: station(mdef.TurnInStation))) is not None:
        record["tin"] = turn_in
    if (nxt := try_(lambda: mdef.NextMissionInChain)) is not None:
        record["next"] = mission_id(nxt)
    # Its DLC (MissionDefinition.DlcExpansion: None for the base game) - the page's "Best now" leaves
    # a DLC's never-offered missions out until that DLC is started
    if (dlc := try_(lambda: mdef.DlcExpansion)) is not None:
        record["dlc"] = try_(lambda: str(dlc._path_name()), "") or def_name(dlc)
    if try_(lambda: bool(mdef.bRepeatable), False):
        record["repeat"] = 1
    if try_(lambda: bool(mdef.bCanBeFailed), False):
        record["fail"] = 1
    _defs[key] = (record, index)
    return record, index


def objective_index(mdef: Any) -> dict[int, int]:
    """A mission's {objective definition address: its index in ObjectiveDefs / ObjectivesProgress}
    (from the cached definition)."""
    return _definition(mdef)[1]


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
    key = (mdef._get_address(), level, try_(lambda: int(mdef.GameStage), 0))
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


Live = tuple[str, tuple[int, ...], tuple[int, ...], bool, int, bool, tuple[str, str] | None, tuple[str, str] | None]
_NOT_STARTED: Live = ("NotStarted", (), (), False, 0, False, None, None)


def _waiting_on(mdef: Any, status: dict[str, str], progress: dict[int, tuple[int, ...]]) -> tuple[str, str] | None:
    """The objective of another mission a mission waits on, besides its Dependencies: its
    ObjectiveDependency {Objective, Status} (tools/probe_quests.txt: None on most; EODS_Complete: that
    objective must be done) - (the objective's text, its mission's id) while it isn't, else None. Done:
    its mission done, or its count reached in that mission's progress (the last pass's, by mission
    address) - property reads only, no function call (tracker.IsMissionObjectiveComplete was one of
    the calls suspected in a game crash). Other statuses: not known yet, not waited on."""
    dep = try_(lambda: mdef.ObjectiveDependency)
    objective = try_(lambda: dep.Objective)
    if objective is None or not str(getattr(try_(lambda: dep.Status), "name", "")).endswith("Complete"):
        return None
    owner = try_(lambda: objective.Outer)
    if owner is None or not hasattr(owner, "ObjectiveDefs"):
        return None
    owner_id = mission_id(owner)
    if status.get(owner_id) == "Complete":
        return None
    _, index = _definition(owner)
    i = index.get(objective._get_address())
    done = progress.get(owner._get_address(), ())
    if i is not None and i < len(done) and done[i] >= (try_(lambda: int(objective.ObjectiveCount), 1) or 1):
        return None
    return _text(objective, "ProgressMessage") or def_name(objective), owner_id


def _live(entry: Any, index: dict[int, int], prev: Live | None, doable: bool,
          status_by_id: dict[str, str] | None = None, progress: dict[int, tuple[int, ...]] | None = None) -> Live:
    """(status, progress per objective, indices of the current step's objectives, offered, level,
    level fixed, where to go (active), the objective it waits on (not started)) - reading only what
    can change, the full pass going over ~290 entries:
    - done: the status only (its progress is read once, when it gets done: final);
    - not started: the status, offered (bHeardKickoff - the giver offered it; unverified in game) and,
      if doable (every mission it needs done), its level: the one it would be fixed at if picked up now
      (its region's current stage, MissionDefinition.GameStage) and the objective it still waits on
      (_waiting_on: its ObjectiveDependency - the game won't offer it before);
    - active (and anything else): everything - progress, the current step (ActiveObjectiveSet +
      SubObjectiveSets), its level (GameStage, fixed when picked up: bGameStageLocked), and where
      to go for it now (active only): the StationOverride of its step's first objective left that has
      one, else the step's (MissionObjective(Set)Definition.StationOverride - tools/probe_quests.txt:
      "Go to Sanctuary" -> Sanctuary). (name, map) or None. Property reads only: pc.GetLevelForMission
      (the level the game says - tools/probe_area.txt) is no longer called, suspected in a game crash.
    Levels: tools/probe_mission_xp_curve.txt."""
    status = _status_name(try_(lambda: entry.Status, ""))
    if status == "Complete":
        if prev is not None and prev[0] == "Complete":
            return prev
        progress = tuple(int(v) for v in try_(lambda: list(entry.ObjectivesProgress), []) or [])
        return status, progress, (), False, 0, False, None, None
    if status == "NotStarted":
        offered = bool(try_(lambda: entry.bHeardKickoff, False))
        level = try_(lambda: int(field(entry.MissionDef, "GameStage")), 0) if doable else 0
        wait = None
        if doable and not offered and status_by_id is not None:
            wait = try_(lambda: _waiting_on(entry.MissionDef, status_by_id, progress or {}))
        return status, (), (), offered, level, False, None, wait
    progress = tuple(int(v) for v in try_(lambda: list(entry.ObjectivesProgress), []) or [])
    current = []
    step_station = obj_station = None
    sets = [try_(lambda: entry.ActiveObjectiveSet)] + list(try_(lambda: list(entry.SubObjectiveSets), []) or [])
    for s in sets:
        if s is None:
            continue
        if step_station is None:
            step_station = try_(lambda s=s: s.StationOverride)
        for obj in try_(lambda s=s: list(s.ObjectiveDefinitions), []) or []:
            if obj is not None and (i := index.get(obj._get_address())) is not None and i not in current:
                current.append(i)
                done = i < len(progress) and progress[i] >= try_(lambda o=obj: int(o.ObjectiveCount), 1)
                if obj_station is None and not done:
                    obj_station = try_(lambda o=obj: o.StationOverride)
    go = None
    if status == "Active":
        if (override := obj_station or step_station) is not None and (info := station(override)) is not None:
            go = (info["a"], info["map"])
    mdef = try_(lambda: entry.MissionDef)
    level = try_(lambda: int(field(mdef, "GameStage")), 0)
    locked = bool(try_(lambda: field(mdef, "bGameStageLocked"), False))
    return status, progress, tuple(current), bool(try_(lambda: entry.bHeardKickoff, False)), level, locked, go, None


class MissionLog:
    """The log's state between passes. What the page gets, in two payloads: `defs_payload()` - the
    definitions (names, texts, objectives: static, only when the list changes) - and `payload()` -
    the live part (status, progress, level, rewards: small, on every change)."""

    def __init__(self) -> None:
        self._records: list[dict[str, Any]] = []  # per MissionList entry (the definition's record)
        self._mdefs: list[Any] = []  # the definitions (static game data)
        self._rewards: dict[int, dict[str, Any]] = {}  # entry -> {player level: reward}
        self._addrs: list[int] = []  # MissionDef address per entry (the fast pass checks the order)
        self._indexes: list[dict[int, int]] = []
        self._live: list[Live] = []
        self._watch: list[int] = []  # entries the fast pass reads: active ones and the tracked one
        self._cycle: dict[str, Any] | None = None  # the full pass under way (step by step)
        self._tracked = ""
        self.dirty = False  # the live part changed since the last payload()
        self.defs_dirty = True  # the list (definitions) changed since the last defs_payload()

    def full(self, tracker: Any, pcs: list[Any] | None = None) -> None:
        """A whole pass at once (tests / tools): step() until the cycle completes."""
        while not self.step(tracker, lambda: pcs or [], budget=1 << 30):
            pass

    @property
    def in_cycle(self) -> bool:
        """A full pass is under way (step() again next tick)."""
        return self._cycle is not None

    def step(self, tracker: Any, pcs: Any, budget: int = STEP_ENTRIES) -> bool:
        """The full pass, a slice at a time: the next `budget` entries (definitions cached, live state);
        True when the cycle is complete - the new state is then applied (rewards: pcs() gives the
        player controllers). The list is fetched from the tracker at each step (nothing held across
        frames but the definitions, static game data); an entry changed under us is caught by the
        next cycle (and the fast pass checks the order)."""
        entries = try_(lambda: tracker.MissionList)
        if entries is None:
            self._cycle = None
            return True
        if self._cycle is None:
            self._cycle = {
                "k": 0, "records": [], "addrs": [], "indexes": [], "live": [], "watch": [], "mdefs": [],
                # the last pass's states: a done one isn't read again; a not-started one's level only if doable
                "previous": {a: st for (_, a), st in zip(self._addrs, self._live, strict=True)},
                "status": {r["i"]: st[0] for r, st in zip(self._records, self._live, strict=True)},
                # the last pass's progress per mission (address): what a mission's objective dependency reads
                "progress": {a: st[1] for (_, a), st in zip(self._addrs, self._live, strict=True)},
            }
        c = self._cycle
        count = try_(lambda: len(entries), 0)
        end = min(count, c["k"] + budget)
        deadline = time.perf_counter() + STEP_SECONDS if budget == STEP_ENTRIES else float("inf")
        for n in range(c["k"], end):
            if time.perf_counter() > deadline:  # out of time: the rest next tick
                end = n
                break
            entry = try_(lambda n=n: entries[n])
            mdef = try_(lambda e=entry: e.MissionDef)
            if mdef is None:
                continue
            record, index = _definition(mdef)
            address = mdef._get_address()
            doable = all(c["status"].get(d) == "Complete" for d in record["deps"]) if c["status"] else True
            state = _live(entry, index, c["previous"].get(address), doable, c["status"], c["progress"])
            c["records"].append(record)
            c["mdefs"].append(mdef)
            c["addrs"].append((n, address))
            c["indexes"].append(index)
            c["live"].append(state)
            if state[0] not in ("NotStarted", "Complete"):
                c["watch"].append(len(c["records"]) - 1)
        c["k"] = end
        if end < count:
            return False
        self._cycle = None
        records, addrs, indexes, live, watch, mdefs = (c[k] for k in ("records", "addrs", "indexes", "live", "watch", "mdefs"))
        if [a for _, a in addrs] != [a for _, a in self._addrs]:
            self.dirty = self.defs_dirty = True
        elif live != self._live:
            self.dirty = True
        self._records, self._addrs, self._indexes, self._live, self._watch = records, addrs, indexes, live, watch
        self._mdefs = mdefs
        self._track(tracker)
        self._update_rewards(pcs() or [])
        return True

    def _update_rewards(self, pcs: list[Any]) -> None:
        """Rewards of the missions doable now (active, or not started with every dependency done),
        the ones a single step away (every dependency done or doable now: the page's "Best now"
        ranking shows them, "after ..."), and the tracked one - per player level (the game scales them
        to the player: computed with a controller of that level; the page picks its selected
        player's). Every player's controller on the host, only your own on a co-op client."""
        by_level: dict[int, Any] = {}
        for pc in pcs:
            level = try_(lambda pc=pc: int(pc.PlayerReplicationInfo.ExpLevel), 0)
            if level > 0:
                by_level.setdefault(level, pc)
        if not by_level:
            return
        records = {r["i"]: r for r in self._records}
        status = {r["i"]: s[0] for r, s in zip(self._records, self._live, strict=True)}

        def doable(mission_id: str) -> bool:
            st = status.get(mission_id)
            # picked up (active, or ready to turn in: ReadyToTurnIn / RequiredObjectivesComplete)
            return st not in (None, "NotStarted", "Complete") or (st == "NotStarted" and all(status.get(d) == "Complete" for d in records[mission_id]["deps"]))

        rewards = {}
        deadline = time.perf_counter() + REWARDS_SECONDS  # new reward function calls: at most this long per cycle
        for k, (record, (st, *_)) in enumerate(zip(self._records, self._live, strict=True)):
            wanted = doable(record["i"]) or record["i"] == self._tracked or (
                st == "NotStarted" and all(status.get(d) == "Complete" or (d in records and doable(d)) for d in record["deps"]))
            if not wanted:
                continue
            per_level = {}
            for level, pc in by_level.items():
                mdef = self._mdefs[k]
                if (mdef._get_address(), level, try_(lambda m=mdef: int(m.GameStage), 0)) not in _rewards and time.perf_counter() > deadline:
                    # out of time for new function calls: the previous value meanwhile, the rest next cycle
                    if (old := self._rewards.get(k, {}).get(str(level))) is not None:
                        per_level[str(level)] = old
                    continue
                if r := _reward(mdef, pc, level):
                    per_level[str(level)] = r
            if per_level:
                rewards[k] = per_level
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
            state = _live(entry, self._indexes[k], self._live[k], True)
            if state[0] == "NotStarted":  # (a tracked one) what it waits on: the full pass's
                state = (*state[:7], self._live[k][7])
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

    def entry_addresses(self) -> list[tuple[int, int]]:
        """(MissionList index, MissionDefinition address) per entry, as of the last full pass."""
        return list(self._addrs)

    def defs_payload(self) -> dict[str, Any]:
        """The definitions, in the list's order (static: sent when the list changes)."""
        self.defs_dirty = False
        return {"missions": self._records}

    def payload(self, level_id: int) -> dict[str, Any]:
        """The live part, per mission by id (the page merges it with the definitions)."""
        self.dirty = False
        missions = []
        for k, (record, (status, progress, current, offered, level, locked, go, wait)) in enumerate(zip(self._records, self._live, strict=True)):
            m = {"i": record["i"], "st": status}
            if level:
                m["ml"] = level  # its level: locked (picked up), else the one it would lock at now
                if locked:
                    m["mlk"] = 1
            if offered:
                m["kick"] = 1
            if (reward := self._rewards.get(k)) is not None:
                m["rw"] = reward
            if progress:
                m["p"] = list(progress)
            if current:
                m["cur"] = list(current)
            if go is not None:
                m["go"] = {"a": go[0], "map": go[1]}  # where to go for it now (active)
            if wait is not None:
                m["wait"] = {"o": wait[0], "m": wait[1]}  # the objective of another mission it waits on
            missions.append(m)
        return {"level": level_id, "tracked": self._tracked or None, "missions": missions,
                "thresholds": try_(difficulty_thresholds, {}) or {}}
