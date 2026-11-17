"""Seasonal events that come back (the offline calendar repeats every year).

The save keeps one entry per event id (RO2_PersistentGameData_Universe::SeasonalEventData, map at
universe+0x1238; tree node: id +0x20, unlocked +0x48, finished +0x49, families +0x28):
  - unlocked: the event's Incrediball families can drop (isSeasonalEventFamilyAvailable) and its intro
    has been shown (RLC_SeasonalEventManager::currentEventIntroHasBeenDisplayed);
  - finished: its families are struck out (isSeasonalEventOfThisFamilyIsFinished).
Ubisoft never ran the same event twice, so the game only creates the entry the first time
(startSeasonalEventFamilyAvailable, when the event screen opens) and never resets it. A returning
event therefore stayed finished: no families, no intro.

1. Ending an event clears "unlocked" as well (its families stop dropping, its intro will show again):
   - stopAllSeasonalEventExceptCurrent 0x14735d0 "strb w23, [x20, #0x49]" (w23 = 1) -> cave writing
     both bytes;
   - stopSeasonalEventFamilyAvailable 0x14e725c "mov w1, #1 ; strb w1, [x0, #0x29]" (x0 = value,
     unlocked +0x28) -> "mov w1, #0x100 ; strh w1, [x0, #0x28]".
2. Opening the screen of an event whose entry is finished (a previous year) starts it again as new:
   startSeasonalEventFamilyAvailable 0x151b9e4 "b.ne <entry exists: return>" -> cave: existing and
   finished -> unlocked = 1, finished = 0 (what a new entry gets), then return.
"""

CAVE = 0xE0AF90            # after store_hooks (0xe0af80..0xe0af90), up to 0xe0b000
CAVE_END = 0xE0B000
STOP_ALL = 0x14735d0
STOP_ALL_ORIG = "97260139"         # strb w23, [x20, #0x49]
STOP_FAMILY = 0x14e725c
STOP_FAMILY_ORIG = "2100805201a40039"   # mov w1, #1 ; strb w1, [x0, #0x29]
START_FAMILY = 0x151b9e4
START_FAMILY_ORIG = "a1070054"     # b.ne 0x151bad8
START_FAMILY_NEW = 0x151b9e8       # entry missing: create it (original path)
START_FAMILY_RETURN = 0x151bad8


def assemble(data):
    import keystone, capstone
    ks = keystone.Ks(keystone.KS_ARCH_ARM64, keystone.KS_MODE_LITTLE_ENDIAN)
    for addr, orig in ((STOP_ALL, STOP_ALL_ORIG), (STOP_FAMILY, STOP_FAMILY_ORIG), (START_FAMILY, START_FAMILY_ORIG)):
        assert data[addr:addr + len(orig) // 2].hex() == orig, f"unexpected bytes at {addr:#x}"
    cave = bytes(ks.asm(f"""
    stop_all:
        strb w23, [x20, #0x49]
        strb wzr, [x20, #0x48]
        b {STOP_ALL + 4:#x}
    start_family:
        b.ne exists
        b {START_FAMILY_NEW:#x}
    exists:
        ldrb w1, [x0, #0x49]
        cbz w1, done
        mov w1, #1
        strh w1, [x0, #0x48]
    done:
        b {START_FAMILY_RETURN:#x}
    """, CAVE)[0])
    assert CAVE + len(cave) <= CAVE_END
    md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)
    start_family = next(i.address for i in md.disasm(cave, CAVE) if i.mnemonic == "b.ne")
    return {
        CAVE: cave,
        STOP_ALL: bytes(ks.asm(f"b {CAVE:#x}", STOP_ALL)[0]),
        STOP_FAMILY: bytes(ks.asm("mov w1, #0x100 ; strh w1, [x0, #0x28]", STOP_FAMILY)[0]),
        START_FAMILY: bytes(ks.asm(f"b {start_family:#x}", START_FAMILY)[0]),
    }
