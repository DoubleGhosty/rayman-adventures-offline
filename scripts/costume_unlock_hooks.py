"""Exclusive costumes: the costumes that only came in a real-money pack or with the Facebook login
are sold for their gem price in the costume shop.

dynamicStore::createInventoryItemsIfNeeded builds the store inventory from the store SDK's catalogue
at each launch. A costume's state (RLC_Costume +0x14) comes from its trade's args[1] (case-insensitive):
"facebook" -> LockedFacebook (4), "starterpack" / "storebundle" -> LockedStoreBundle (5), anything
else -> NotOwned (2), then Owned (3) for the costumes the player has. The SDK keeps its own copy of
the catalogue (encrypted files/msdk) and does not always take a changed one, so the state is decided
here rather than in our catalogue.

Hook at 0x1842244 "str w23, [x19, #0x14]" (x19 = the new RLC_Costume, w23 = its state, x22 = the
msdk_SecondaryStoreItem trade: +0x18 -> price item, item id at +0; +0x20 price): a costume in state
4 or 5 whose price is in gems (item 3594) becomes NotOwned (2). Event costumes (price in event
currency, item 4178) stay locked: the event shops sell them. Raybox (Rayman_Globox) keeps its
catalogue price of 1 gem, as it was a free gift for logging in to Facebook.
21 costumes: Barbara Assassin, bondgirl, WeForest, Christmas; Globox Cromagnon, Vaas, BigFoot,
WeForest, Splinter; Rayman Raybox, Assassin, Splinter, Vaas, Christmas, Dark, WeForest, Chinese,
Persia; Teensy Cromagnon, Ninja, WeForest.
"""

CAVE = 0xFDC110             # zero run 0xfdc104..0xfdd0f8, nothing branches into it
CAVE_END = 0xFDD0F8
HOOK = 0x1842244
HOOK_ORIG = "771600b9"      # str w23, [x19, #0x14]
HOOK_RETURN = 0x1842248
GEMS_ITEM = 3594


def assemble(data):
    import keystone
    ks = keystone.Ks(keystone.KS_ARCH_ARM64, keystone.KS_MODE_LITTLE_ENDIAN)
    got = data[HOOK:HOOK + 4].hex()
    assert got == HOOK_ORIG, f"unexpected bytes at {HOOK:#x}: {got}"
    assert data[CAVE:CAVE_END] == bytes(CAVE_END - CAVE), "costume unlock cave not empty"
    src = f"""
    cmp w23, #4
    b.lo store
    cmp w23, #5
    b.hi store
    ldr x2, [x22, #0x18]
    cbz x2, store
    ldr w2, [x2]
    mov w3, #{GEMS_ITEM}
    cmp w2, w3
    b.ne store
    mov w23, #2
store:
    str w23, [x19, #0x14]
    b {HOOK_RETURN:#x}
"""
    cave = bytes(ks.asm(src, CAVE)[0])
    assert CAVE + len(cave) <= CAVE_END
    return {CAVE: cave, HOOK: bytes(ks.asm(f"b {CAVE:#x}", HOOK)[0])}
