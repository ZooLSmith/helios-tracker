"""
Borderlands 1's packages (the original game: file version 584, licensee 57 - WillowGame/CookedPC): formats.upk.Package with
what differs from BL2's format (832), nothing else. The Game of the Year Enhanced edition's (594, licensee 58): the same
but for an enum property's tag, which carries its enum's name as BL2's does - read by the file's own version. Read
offline from the game's files (.agent/bl1.md "Game files"). Pure Python, no SDK.
"""

import struct

from ....formats.upk import TAG, Package


class Bl1Package(Package):
    VERSION = 584
    TEXTURE_HEADS = (32,)  # source art (an empty bulk data header, 16 bytes) and a guid (16), then the mips
    SUMMARY_TABLES = 4  # the thumbnail table offset only (the import / export guid tables: from version 623)
    BOOL_SIZE = 4  # a UBOOL (1 byte from 673)
    NAMED_TYPES = ("StructProperty",)  # a ByteProperty's enum name: from 594 (below)
    # the Enhanced edition's packages: a ByteProperty's tag names its enum (a texture's Format: EPixelFormat, then
    # PF_DXT5 - FX_Items.Textures.Credits, offline 2026-10-04); everything the mod reads otherwise the same
    ENHANCED = 594

    def _reads(self, version: int) -> bool:
        return version in (self.VERSION, self.ENHANCED)

    def _read_summary(self) -> None:
        super()._read_summary()
        if self.file_version >= self.ENHANCED:
            self.NAMED_TYPES = Package.NAMED_TYPES

    def _index_chunk(self, uoff: int, usize: int, coff: int, csize: int) -> None:
        # a chunk not worth compressing is stored raw: its compressed size its size, no chunk tag (W_Arid_Farmstead's
        # last four chunks) - BL2 never does
        self.f.seek(coff)
        if csize == usize and self.f.read(4) != struct.pack("<I", TAG):
            self.blocks.append((uoff, usize, coff, -1))
            return
        super()._index_chunk(uoff, usize, coff, csize)

    def actor_properties(self, data: bytes) -> tuple[dict[str, tuple[str, bytes]], int]:
        """An actor's tagged properties: its data starts with its state frame - its state (2 refs), an 8-byte probe
        mask, a 2-byte latent action, its state stack (a count: empty in the actors read so far), a code offset - then
        its NetIndex (the LevelLandmarkAnchors of every base level: properties at 30)."""
        stack = struct.unpack_from("<i", data, 18)[0]
        if stack:
            raise ValueError(f"an actor with a state stack ({stack}): its layout isn't known")
        return self.properties(data, 4 + 4 + 8 + 2 + 4 + 4 + 4)
