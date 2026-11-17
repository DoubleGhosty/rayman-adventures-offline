"""Creatures chosen by the game for server answers that only carry "pick one for me".

Ubisoft's server chose the creature of several eggs. The embedded server has no creature
database logic, so it answers creatureId = invalid with rarity 6 (Creature_Rarity::unknown) and these
hooks let the game pick with its own RLC_CreatureManager::HatchSimulation(acquisition,
graphicalFamily, rarity, forceNew). With rarity 6 it draws the rarity with its own weights
(HatchCreature_PickRarity) and removes creatures of locked regions, seasonal families and
duplicates - what it does for the normal adventure eggs.

1. 0x16e3b7c, RLC_AdventureManager::onGameServerRequestDone, MagnifyingGlassNextAdventure
   (magnifying glass: eggs of the next adventures): per result (stride 0x34: creatureId +0,
   rarity +4), "ldr w1, [x1, x22]" -> creatureId; picked when invalid (acquisition 1).
2. 0x1687964, RLC_GS_AdventureMap::onGameServerRequestDone, GetCharlie (hidden extra egg of an
   adventure): charlieResult {charlie +0 (1 = present), charlieCreatureId +4}; picked when
   charlie == 1 and the id is invalid (acquisition 2).
graphicalFamily = RLC_AdventureManager::getCurrentAdventureRegion() (the region of the eggs
of this adventure; the lucky ticket hook keeps the developers' choice, Universe+0x934).
"""

CAVE = 0xE0AC00            # debug_hooks.py stops at 0xe0ac00, incubator_hooks.py starts at 0xe0af00
CAVE_END = 0xE0AF00
HATCH_SIMULATION = 0x16922cc
CREATURE_MANAGER_GOT = 0x24a8530
ADVENTURE_MANAGER_GOT = 0x24b3338   # -> RLC_AdventureManager*
GET_CURRENT_ADVENTURE_REGION = 0x162f2b8

MAGNIFY = 0x16e3b7c        # ldr w1, [x1, x22]
MAGNIFY_ORIG = "216876b8"
MAGNIFY_RESUME = 0x16e3b80
CHARLIE = 0x1687964        # ldr w1, [x19, #4]
CHARLIE_ORIG = "610640b9"
CHARLIE_RESUME = 0x1687968


def _pick(acq, rarity_asm):
    """HatchSimulation(cm, acq, current adventure region, rarity, 0); result in w0.
    rarity_asm must leave the rarity in w3 (it runs after the region call, which clobbers x0-x18)."""
    return f"""
        adrp x0, {ADVENTURE_MANAGER_GOT & ~0xfff:#x}
        ldr x0, [x0, #{ADVENTURE_MANAGER_GOT & 0xfff:#x}]
        ldr x0, [x0]
        bl {GET_CURRENT_ADVENTURE_REGION:#x}
        mov w2, w0
        {rarity_asm}
        mov w1, #{acq}
        mov w4, #0
        adrp x0, {CREATURE_MANAGER_GOT & ~0xfff:#x}
        ldr x0, [x0, #{CREATURE_MANAGER_GOT & 0xfff:#x}]
        ldr x0, [x0]
        bl {HATCH_SIMULATION:#x}
"""


def assemble(data):
    import keystone, capstone
    ks = keystone.Ks(keystone.KS_ARCH_ARM64, keystone.KS_MODE_LITTLE_ENDIAN)
    assert data[MAGNIFY:MAGNIFY + 4].hex() == MAGNIFY_ORIG, "unexpected bytes (magnifying glass)"
    assert data[CHARLIE:CHARLIE + 4].hex() == CHARLIE_ORIG, "unexpected bytes (charlie)"
    # magnifying glass: x1 = results, x22 = i * 0x34, x20 = vector (+0x10 data), x25 = EggData
    magnify = f"""
        add x9, x1, x22
        ldr w1, [x9]
        cmn w1, #1
        b.ne mg_done
        {_pick(1, "ldr x9, [x20, #0x10]; add x9, x9, x22; ldr w3, [x9, #4]")}
        ldr x9, [x20, #0x10]
        add x9, x9, x22
        str w0, [x9]
        mov w1, w0
        mov x0, x25
        mov w2, #1
        mov w3, #0
        mov x5, #0x34
    mg_done:
        b {MAGNIFY_RESUME:#x}
    """
    cave = bytes(ks.asm(magnify, CAVE)[0])
    charlie_at = CAVE + len(cave)
    # charlie: x19 = charlieResult
    charlie = f"""
        ldr w1, [x19, #4]
        ldr w0, [x19]
        cmp w0, #1
        b.ne ch_done
        cmn w1, #1
        b.ne ch_done
        {_pick(2, "mov w3, #6")}
        str w0, [x19, #4]
        mov w1, w0
    ch_done:
        ldr w0, [x19]
        b {CHARLIE_RESUME:#x}
    """
    cave += bytes(ks.asm(charlie, charlie_at)[0])
    assert CAVE + len(cave) <= CAVE_END
    md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)
    for i in md.disasm(cave, CAVE):
        if i.mnemonic.startswith(("b.", "cbz", "cbnz")):
            assert CAVE <= int(i.op_str.split("#")[-1], 16) < CAVE_END, f"far conditional branch: {i}"
    return {
        CAVE: cave,
        MAGNIFY: bytes(ks.asm(f"b {CAVE:#x}", MAGNIFY)[0]),
        CHARLIE: bytes(ks.asm(f"b {charlie_at:#x}", CHARLIE)[0]),
    }


if __name__ == "__main__":
    import capstone, os
    lib = os.path.join(os.path.dirname(__file__), "..", "binaries", "libuaf_original.so")
    md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)
    for a, b in assemble(open(lib, "rb").read()).items():
        print(f"; {a:#x}")
        for i in md.disasm(b, a):
            print(f"  {i.address:#x}: {i.mnemonic} {i.op_str}")
