"""Borderlands 1's skills: what differs from Borderlands 2's (games/bl2/skills.py) - .agent/bl1.md.
Moved from games.py (profiles.md step 4: a pure move)."""

import re
from typing import Any

from ..bl2.skills import Skills

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

    def read(self, ctrl: Any, player: dict[str, Any], bonuses: dict[str, Any]) -> None:
        # No PlayerSkillTree: the controller's PlayerSkills[] and SkillTreeBranches[] (tools/probes/probe_bl1_skills.txt) -
        # inspector._skills_from_player_skills; its branches' names: the skill menu's (branch_names)
        from ...inspector import _skills_from_player_skills  # noqa: PLC0415

        _skills_from_player_skills(ctrl, player, bonuses, self.branch_names(ctrl), self._cached_skill_icons(ctrl))

    def _cached_skill_icons(self, ctrl: Any) -> dict[tuple[str, int, int], str]:
        """skill_icons, once per character (static: its class's layout - every players pass walked it: 3-4 ms)."""
        key = int(ctrl.PlayerClass.CharacterName)
        if (icons := self._skill_icons.get(key)) is None:
            icons = self._skill_icons[key] = self.skill_icons(ctrl)
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

    def skill_icons(self, ctrl: Any) -> dict[tuple[str, int, int], str]:
        """The tree's cells' icons: (branch, tier, cell) -> a menu icon path ("menu.skills.mordecai.icon17.on.off":
        bl1map.MENU_ICON, served as /icon/<path>.png). No icon of their own on the skills (SkillDefinition
        .ScaleformFrameName: the HUD's popups, a few skills): the skill menu's cells - the class's SkillTreeLayout
        (ui_skill_tree.upk: <Branch>.Tiers[].Skills[], one SkillTreeNavDefinition per cell, in order) names each cell's
        clip (IconClipName, "icon17"), placed in the player's frame of the skill clip, drawn at its frame
        SkillTreeGFxDefinition.IconOnName ("on") - what its IconOffName frame shows too (its drawing, not the state's
        tile: bl1map.clip_icon) - offline, .agent/bl1.md."""
        import unrealsdk  # noqa: PLC0415

        from ...inspector import BL1_BRANCHES  # noqa: PLC0415

        clip, frame = self._skill_clip(ctrl)
        layout = ctrl.PlayerClass.PlayerSkillSet.SkillTreeLayout
        movie_def = unrealsdk.find_class("SkillTreeGFxDefinition").ClassDefaultObject
        on, off = str(movie_def.IconOnName), str(movie_def.IconOffName)
        icons = {}
        for branch, field in BL1_BRANCHES.items():
            for tier, tier_data in enumerate(getattr(layout, field).Tiers):
                for cell, nav in enumerate(tier_data.Skills):
                    if nav is not None:
                        icons[(branch, tier, cell)] = f"menu.{clip}.{frame}.{nav.IconClipName}.{on}.{off}"
        return icons

    def branch_names(self, ctrl: Any) -> dict[str, str]:
        """The player's tree branches' names, as the skill menu shows them ("SNIPER"...: BL1_BRANCH_TEXTS' keys -> the
        game's text), {} until its movie is read. No branch definition has one: the menu's movie sets them, per
        character (tools/probes/probe_bl1_branches.txt; WillowGame.u, its movie, DefaultGame.ini - offline):
        SkillTreeGFxHelper.GetCharacterName() (a switch on its CurrentCharacter, the class's CharacterName: 1 ->
        "mordecai") is the frame its skill clip goes to (SkillTreeGFxDefinition.SkillMovieClip, "skills"); that frame's
        ActionScript sets tree1.text to "$<StringAliasMap:skills_hunter_branch1>"; the alias map
        (WillowUIDataStore_StringAliasMap.MenuInputMapArray, from DefaultGame.ini) has it as
        "<Strings:WillowGame.SkillTreeMovie.SkillsHunterBranch1String>", localized: SNIPER."""
        import unrealsdk  # noqa: PLC0415

        from ... import bl1map, gamedir  # noqa: PLC0415

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
