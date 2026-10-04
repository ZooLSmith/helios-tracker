"""Borderlands 1's skills: what differs from Borderlands 2's (games/bl2/skills.py) - .agent/bl1.md."""

import re
from typing import Any

from ..bl2.skills import Skills

BRANCHES = {"SKILLBRANCH_First": "FirstBranch", "SKILLBRANCH_Left": "LeftBranch", "SKILLBRANCH_Middle": "MiddleBranch",
            "SKILLBRANCH_Right": "RightBranch"}  # a branch's state -> its static data in the class's PlayerSkillSet
# a tree branch -> the skill clip's text field naming it: tree1..3 sit under treeLeft / treeCenter / treeRight (the
# skill clip's placements, x 21.75 / 199.75 / 378.75 against 17.2 / 195.4 / 339.2 - its movie, offline)
BL1_BRANCH_TEXTS = {"SKILLBRANCH_Left": "tree1.text", "SKILLBRANCH_Middle": "tree2.text", "SKILLBRANCH_Right": "tree3.text"}
BL1_ALIAS = re.compile(r"\$<StringAliasMap:([^>]+)>")  # a Scaleform text naming an alias map entry
BL1_STRINGS = re.compile(r"<Strings:([^.>]+)\.([^.>]+)\.([^>]+)>")  # a localized text's markup: package.section.key


class Bl1Skills(Skills):
    """Borderlands 1's skills."""

    def __init__(self, profile: Any) -> None:
        super().__init__(profile)
        self._branch_names: dict[int, dict[str, str]] = {}  # CharacterName -> its branches' names (branch_names)
        self._skill_icons: dict[int, dict[tuple[str, int, int], str]] = {}  # CharacterName -> its cells' icons (skill_icons)
        self._skill_clips: dict[int, tuple[str, str]] = {}  # CharacterName -> (the skill clip, its frame) (_skill_clip)

    def icon(self, skill_def: Any) -> str:
        return ""  # (no skill icon textures served: its tree's icons are its skill menu's - _read_skill_icons)

    def read(self, ctrl: Any, player: dict[str, Any], bonuses: dict[str, Any]) -> None:
        # No PlayerSkillTree: the controller's PlayerSkills[] and SkillTreeBranches[] (tools/probes/probe_bl1_skills.txt) -
        # _player_skills; its branches' names: the skill menu's (_read_branch_names)
        self._player_skills(ctrl, player, bonuses, self._read_branch_names(ctrl), self._cached_skill_icons(ctrl))

    def _player_skills(self, ctrl: Any, player: dict[str, Any], bonuses: dict[str, list[list[Any]]] | None = None,
                       branch_names: dict[str, str] | None = None,
                       icons: dict[tuple[str, int, int], str] | None = None) -> None:
        """A player's skill tree, as the inspector's _skills's record (tools/probes/probe_bl1_skills.txt): no PlayerSkillTree -
        the controller's SkillTreeBranches[] = {BranchIndex (SKILLBRANCH_First: the action skill alone; Left / Middle / Right),
        PointsSpentInBranch, Tiers[]: {TierIndex, PlayerSkillIndexList (-1: an empty cell)}}, each index into PlayerSkills[] =
        {Definition, Grade...} (the tree's ~25 among input "skills", proficiencies...); the points a tier asks: the class's
        PlayerSkillSet's <Branch>.Tiers[].PointsToUnlockNextTier (5). Its branches' names: `branch_names` (the skill menu's -
        _read_branch_names), else their own technical name, marked as a guess; its cells' icons: `icons` ((branch, tier,
        cell) -> an icon path - _read_skill_icons)."""
        from ... import inspector  # noqa: PLC0415
        from ...inspector import _enum_name, _skill_stats, _skills_cache, _static_info  # noqa: PLC0415
        from ...util import def_name, named, try_  # noqa: PLC0415

        entries = try_(lambda: list(ctrl.PlayerSkills), None) if ctrl is not None else None
        branch_states = try_(lambda: list(ctrl.SkillTreeBranches), None) if ctrl is not None else None
        if not entries or not branch_states:
            player["skillsWhy"] = "unavailable" if player["local"] else "coopClient"
            return
        points = sum(try_(lambda b=b: int(b.PointsSpentInBranch), 0) or 0 for b in branch_states)
        bonuses = bonuses or {}
        branch_names, icons = branch_names or {}, icons or {}
        cache_key = (points, tuple(sorted((k, tuple(map(tuple, v))) for k, v in bonuses.items())), tuple(sorted(branch_names.items())))
        cached = _skills_cache.get(ctrl)
        if cached is not None and cached[0] == cache_key:
            player.update(cached[1])
            return
        skipped = inspector._items_pass["skipped"]
        skill_set = try_(lambda: ctrl.PlayerClass.PlayerSkillSet)
        trees = []
        for state in branch_states:
            branch_name = _enum_name(try_(lambda s=state: s.BranchIndex, ""))
            static_tiers = try_(lambda n=branch_name: list(getattr(skill_set, BRANCHES[n]).Tiers), []) or []
            tiers, flat, spent = [], [], 0
            for tier in try_(lambda s=state: list(s.Tiers), []) or []:
                index = try_(lambda t=tier: int(t.TierIndex), 0)
                need = try_(lambda i=index: int(static_tiers[i].PointsToUnlockNextTier), 0) if index < len(static_tiers) else 0
                cells: list[dict[str, Any] | None] = []
                for cell, slot in enumerate(try_(lambda t=tier: list(t.PlayerSkillIndexList), []) or []):
                    entry = entries[slot] if 0 <= slot < len(entries) else None
                    sd = try_(lambda e=entry: e.Definition) if entry is not None else None
                    if sd is None:
                        cells.append(None)
                        continue
                    info = _static_info(sd, lambda d: {
                        **named(try_(lambda: str(d.SkillName), ""), def_name(d)),
                        "m": try_(lambda: int(d.MaxGrade), 0),
                        "d": try_(lambda: str(d.SkillDescription), ""),
                    })
                    grade = try_(lambda e=entry: int(e.Grade), 0) or 0
                    skill = {**info, "g": grade, "t": index + 1}
                    if ic := icons.get((branch_name, index, cell)):
                        skill["ic"] = ic
                    sources = bonuses.get(try_(lambda: str(sd.Name), "").lower(), [])  # (a class mod's ranks, as BL2's)
                    if bonus := sum(ranks for ranks, _name in sources):
                        skill["b"], skill["bs"] = bonus, sources
                    effective = grade + bonus if grade > 0 else 0
                    if effective > 0 and (fx := _skill_stats(sd, ctrl, effective)):
                        skill["fx"] = fx
                    if grade < info["m"] and (fxn := _skill_stats(sd, ctrl, grade + bonus + 1)):
                        skill["fxn"] = fxn
                    cells.append(skill)
                    flat.append(skill)
                    spent += grade
                tiers.append({"need": need, "cells": cells})
            if not flat:
                continue
            tree = {**named(branch_names.get(branch_name, ""), branch_name), "pts": spent, "skills": flat, "tiers": tiers}
            if branch_name == "SKILLBRANCH_First":
                tree["root"] = True  # (the action skill's: not a tree of its own)
            trees.append(tree)
        result = {"skills": trees, "skillPoints": points}
        if inspector._items_pass["skipped"] == skipped:  # (complete - else again at the next pass)
            _skills_cache.put(ctrl, (cache_key, result, 0.0))
        player.update(result)

    def _cached_skill_icons(self, ctrl: Any) -> dict[tuple[str, int, int], str]:
        """_read_skill_icons, once per character (static: its class's layout - every players pass walked it: 3-4 ms)."""
        key = int(ctrl.PlayerClass.CharacterName)
        if (icons := self._skill_icons.get(key)) is None:
            icons = self._skill_icons[key] = self._read_skill_icons(ctrl)
        return icons

    def _skill_clip(self, ctrl: Any) -> tuple[str, str]:
        """The skill menu's clip and the player's frame of it: ("skills", "mordecai") - SkillTreeGFxDefinition
        .SkillMovieClip, and SkillTreeGFxHelper.GetCharacterName() (a switch on CurrentCharacter: the class's
        CharacterName - on one we construct; tools/probes/probe_bl1_branches.txt). Its Flash_SetCharacter's gotoAndStop."""
        import unrealsdk  # noqa: PLC0415

        character = ctrl.PlayerClass.CharacterName
        if (found := self._skill_clips.get(int(character))) is None:
            helper = unrealsdk.construct_object("SkillTreeGFxHelper", ctrl)
            helper.CurrentCharacter = character
            clip = str(unrealsdk.find_class("SkillTreeGFxDefinition").ClassDefaultObject.SkillMovieClip)
            found = self._skill_clips[int(character)] = (clip, str(helper.GetCharacterName()))
        return found

    def _read_skill_icons(self, ctrl: Any) -> dict[tuple[str, int, int], str]:
        """The tree's cells' icons: (branch, tier, cell) -> a menu icon path ("menu.skills.mordecai.icon17.on.off":
        bl1map.MENU_ICON, served as /icon/<path>.png). No icon of their own on the skills (SkillDefinition
        .ScaleformFrameName: the HUD's popups, a few skills): the skill menu's cells - the class's SkillTreeLayout
        (ui_skill_tree.upk: <Branch>.Tiers[].Skills[], one SkillTreeNavDefinition per cell, in order) names each cell's
        clip (IconClipName, "icon17"), placed in the player's frame of the skill clip, drawn at its frame
        SkillTreeGFxDefinition.IconOnName ("on") - what its IconOffName frame shows too (its drawing, not the state's
        tile: bl1map.clip_icon) - offline, .agent/bl1.md."""
        import unrealsdk  # noqa: PLC0415

        clip, frame = self._skill_clip(ctrl)
        layout = ctrl.PlayerClass.PlayerSkillSet.SkillTreeLayout
        movie_def = unrealsdk.find_class("SkillTreeGFxDefinition").ClassDefaultObject
        on, off = str(movie_def.IconOnName), str(movie_def.IconOffName)
        icons = {}
        for branch, field in BRANCHES.items():
            for tier, tier_data in enumerate(getattr(layout, field).Tiers):
                for cell, nav in enumerate(tier_data.Skills):
                    if nav is not None:
                        icons[(branch, tier, cell)] = f"menu.{clip}.{frame}.{nav.IconClipName}.{on}.{off}"
        return icons

    def _read_branch_names(self, ctrl: Any) -> dict[str, str]:
        """The player's tree branches' names, as the skill menu shows them ("SNIPER"...: BL1_BRANCH_TEXTS' keys -> the
        game's text), {} until its movie is read. No branch definition has one: the menu's movie sets them, per
        character (tools/probes/probe_bl1_branches.txt; WillowGame.u, its movie, DefaultGame.ini - offline):
        SkillTreeGFxHelper.GetCharacterName() (a switch on its CurrentCharacter, the class's CharacterName: 1 ->
        "mordecai") is the frame its skill clip goes to (SkillTreeGFxDefinition.SkillMovieClip, "skills"); that frame's
        ActionScript sets tree1.text to "$<StringAliasMap:skills_hunter_branch1>"; the alias map
        (WillowUIDataStore_StringAliasMap.MenuInputMapArray, from DefaultGame.ini) has it as
        "<Strings:WillowGame.SkillTreeMovie.SkillsHunterBranch1String>", localized: SNIPER."""
        import unrealsdk  # noqa: PLC0415

        from ... import gamedir  # noqa: PLC0415
        from .files import bl1map  # noqa: PLC0415

        cache_key = int(ctrl.PlayerClass.CharacterName)
        if (names := self._branch_names.get(cache_key)) is not None:
            return names
        cooked = gamedir.cooked_dir()
        if cooked is None:
            return {}
        clip, frame = self._skill_clip(ctrl)
        texts = bl1map.clip_texts_later(cooked, clip, frame)
        if texts is None:
            return {}  # (being read: asked again at the next read)
        aliases = {str(e.FieldName): str(e.MappedText)
                   for e in unrealsdk.find_class("WillowUIDataStore_StringAliasMap").ClassDefaultObject.MenuInputMapArray}
        localize = unrealsdk.find_class("Object").ClassDefaultObject.Localize
        names = {}
        for branch, field in BL1_BRANCH_TEXTS.items():
            alias = BL1_ALIAS.fullmatch(texts.get(field, ""))
            strings = BL1_STRINGS.fullmatch(aliases.get(alias.group(1), "")) if alias else None
            if strings:
                package, section, key = strings.groups()
                names[branch] = str(localize(section, key, package))
        self._branch_names[cache_key] = names
        return names

    def action_locked(self, pc: Any) -> bool:
        # Its action skill: PlayerSkills[ActionSkillPlayerSkillIndex] (Bloodwing, index 36), Grade 0 until the first
        # skill point unlocks it (probe_bl1_skills.txt: Lv 5, 1 point unspent - the page said "ready")
        return int(pc.PlayerSkills[int(pc.ActionSkillPlayerSkillIndex)].Grade) == 0
