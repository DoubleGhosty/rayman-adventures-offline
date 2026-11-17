"""Shop guards for packs that no longer exist offline.

1. RLC_InAppPurchaseManager::tryBuyEasterEggPack (0x168206c), the "buy" button of the seasonal
   event's "not enough currency" popup (RLC_SeasonalEventManager::updateNotEnoughSeasonalCurrencyPopup).
   The packs it sells ("Easter Eggs" 400 / 700 / 1450 / 3200 / 6650 of seasonal currency) were paid
   with real money through Google Play: offline the store content has none, getItemTypeAtIndex
   <RLC_EasterEggPack> returns null and "ldr w1, [x22, #8]" crashed the game (SIGSEGV, seen on WSA
   2026-11-17 when buying in the event shop without enough currency). Now a missing pack returns
   false (w19 = 0 there: dynamicStore::isIAPRestricted was false) and the popup stays open.
"""

CAVE = 0xE0AF80            # free since the lucky ticket hooks moved to 0xd6a290 (up to 0xe0b000)
CAVE_END = 0xE0B000
EASTER_PACK = 0x168212c    # ldr w1, [x22, #8]
EASTER_PACK_ORIG = "c10a40b9"
EASTER_PACK_RESUME = 0x1682130
EASTER_PACK_FAIL = 0x1682138   # mov w0, w19 ; epilogue


def assemble(data):
    import keystone
    ks = keystone.Ks(keystone.KS_ARCH_ARM64, keystone.KS_MODE_LITTLE_ENDIAN)
    assert data[EASTER_PACK:EASTER_PACK + 4].hex() == EASTER_PACK_ORIG, "unexpected bytes (tryBuyEasterEggPack)"
    cave = bytes(ks.asm(f"""
        cbz x22, no_pack
        ldr w1, [x22, #8]
        b {EASTER_PACK_RESUME:#x}
    no_pack:
        b {EASTER_PACK_FAIL:#x}
    """, CAVE)[0])
    assert CAVE + len(cave) <= CAVE_END
    return {CAVE: cave, EASTER_PACK: bytes(ks.asm(f"b {CAVE:#x}", EASTER_PACK)[0])}
