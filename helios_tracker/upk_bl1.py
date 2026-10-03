"""
Borderlands 1's packages (the original game: file version 584, licensee 57 - WillowGame/CookedPC): upk.Package with
what differs from BL2's format (832), nothing else. Read offline from the game's files (.agent/bl1.md "Game files").
Pure Python, no SDK.
"""

import struct

from .upk import TAG, Package


class Bl1Package(Package):
    VERSION = 584
    TEXTURE_HEADS = (32,)  # source art (an empty bulk data header, 16 bytes) and a guid (16), then the mips
    SUMMARY_TABLES = 4  # the thumbnail table offset only (the import / export guid tables: from version 623)
    BOOL_SIZE = 4  # a UBOOL (1 byte from 673)
    NAMED_TYPES = ("StructProperty",)  # a ByteProperty's enum name: from 633

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
