"""Real-money packs paid with gems (the catalogue side is scripts/store_packs.py).

How the game buys a real-money pack: dynamicStore::buyPrimaryItem(trade) asks the game server
userprofile/stat, then onGameServerRequestDone registers a msdkRequestListenerBuyPrimaryStoreProduct
for the pack (msdk_PrimaryStoreItem). Its constructor starts the Google Play purchase (0x19f2c38),
and dynamicStore::update calls its update() every frame until it returns 2 or 4: update() polls
the purchase and, once it is over, passes the msdk_PrimaryPurchaseResult {u32 status,
msdk_PrimaryStoreItem*} to dynamicStore::onBuyPrimaryItemResult, which hands the status to
RLC_InventoryManager::onPurchaseResult: 0 bought, 1 "already bought, credited for free" (text
0x428), 2 text 0x2fb, 3 cancelled by the player (no message), 0xb text 0x7bf, else an error. On a
purchase the Mobile SDK has already credited the pack's items; onBuyPrimaryItemResult then
refreshes the inventory, tells the game server about the special packs and shows what the
difference with the items before the purchase (snapshot taken by buyPrimaryItem) brought.

Patched:
  - constructor (0x18347a8, "b 0x19f2c38"): ret, no Google Play purchase;
  - update() (0x1841890): replaced by the cave below, which ends the purchase at once:
      price = the pack's "price" (msdk_PrimaryStoreItem +8 -> product, float at +0x18);
      not enough gems (dynamicStore::getUserGems): the game's "not enough gems" popup
        (RLC_InAppPurchaseManager::openNotEnoughGemsPopup, RLC_BuyInfo.price is the only field it
        reads) and the purchase is cancelled (status 3);
      else creditGems(-price), creditItem(getOldItemId(id), amount) for each item of the pack
        (msdk_PrimaryStoreItem +0x10 -> {u32 count, items}, 0x30 bytes each: id +0, amount
        +0x28), and the purchase is bought (status 0);
      then onBuyPrimaryItemResult(result) as after a Google Play purchase, and return 2.
  - openNotEnoughGemsPopup (0x168137c): it offers the gem pack that would be enough, and with no
    gem pack at all (offline) it showed RLC_Incubator::showPopupError(0x1d6), "Échec de la
    connexion au serveur" (whatever was bought with too few gems: elixirs, tickets, packs...).
    Now the game's infotext 0x13d "PAS ASSEZ DE GEMMES !", which the same function shows when the
    gem shop is forbidden.
  - RLC_InAppPurchaseManager::generateBarredPrice (0x169c584): the struck-through price of a
    discounted special pack is made from the pack's price text, cut at the digits: the text
    between them ("4,99 €" -> ",", " €") gives the decimal separator and the currency,
    tokens[n-2] and tokens[n-1]. "2160 gemmes" has a single token: tokens[-1] crashed when the
    special pack menu opened. With fewer than 2 tokens the price is now "<whole number><token>"
    ("4320 gemmes").
"""

CAVE = 0xFDC200             # zero run 0xfdc104..0xfdd0f8 (costume_unlock_hooks.py uses 0xfdc110..0xfdc200)
CAVE_END = 0xFDD0F8
CTOR_BUY = 0x18347A8        # msdkRequestListenerBuyPrimaryStoreProduct::ctor, "b 0x19f2c38"
CTOR_BUY_ORIG = "24f90614"
UPDATE = 0x1841890          # msdkRequestListenerBuyPrimaryStoreProduct::update, "sub sp, sp, #0x40"
UPDATE_ORIG = "ff0301d1"

GET_USER_GEMS = 0x1841CB8   # dynamicStore::getUserGems()
CREDIT_GEMS = 0x1840F54     # dynamicStore::creditGems(int)
CREDIT_ITEM = 0x1840CC0     # dynamicStore::creditItem(old item id, amount)
GET_OLD_ITEM_ID = 0x18366FC # dynamicStore::getOldItemId(id) (static)
ON_BUY_RESULT = 0x184118C   # dynamicStore::onBuyPrimaryItemResult(msdk_PrimaryPurchaseResult&)
NOT_ENOUGH_GEMS = 0x1681284 # RLC_InAppPurchaseManager::openNotEnoughGemsPopup(const RLC_BuyInfo&)
IAP_MANAGER_GOT = 0x24AA8A8 # -> RLC_InAppPurchaseManager* global
NO_GEM_PACK = 0x168137C     # openNotEnoughGemsPopup, no gem pack: "adrp x0, #0x24b9000" (showPopupError)
NO_GEM_PACK_ORIG = "c0710090"
NO_GEM_PACK_DONE = 0x16815DC
OPEN_INFOTEXT = 0x165D3C4   # RLC_InAppPurchaseManager::openInfotext(u32 text id)
NOT_ENOUGH_GEMS_TEXT = 0x13D
BARRED = 0x169C584          # generateBarredPrice, "ldr x0, [sp, #0x90]" (token count) before tokens[n-2]
BARRED_ORIG = "e04b40f9"
BARRED_RESUME = 0x169C588   # "cmp w0, #2"
BARRED_DONE = 0x169C648     # result = string at sp+0x148, then the function's cleanup
STRING8_CTOR = 0xC96DF0     # ITF::String8::String8()
SET_TEXT_FORMAT = 0x18B1BA0 # ITF::String8::setTextFormat(fmt, ...)
EMPTY_CSTR_GOT = 0x24BDAB0  # -> "" (String8 without text)
FMT_S_S = 0x1E53360         # "%s%s"


def assemble(data):
    import keystone
    ks = keystone.Ks(keystone.KS_ARCH_ARM64, keystone.KS_MODE_LITTLE_ENDIAN)
    for addr, orig in ((CTOR_BUY, CTOR_BUY_ORIG), (UPDATE, UPDATE_ORIG), (NO_GEM_PACK, NO_GEM_PACK_ORIG),
                       (BARRED, BARRED_ORIG)):
        got = data[addr:addr + 4].hex()
        assert got == orig, f"unexpected bytes at {addr:#x}: {got}"
    assert data[CAVE:CAVE_END] == bytes(CAVE_END - CAVE), "pack purchase cave not empty"
    src = f"""
    stp x29, x30, [sp, #-0x70]!
    stp x19, x20, [sp, #0x10]
    stp x21, x22, [sp, #0x20]
    stp x23, x24, [sp, #0x30]
    mov x29, sp
    ldr x19, [x0, #8]
    ldr x20, [x0, #0x10]
    mov w21, #3
    cbz x20, finish
    ldr x0, [x20, #8]
    cbz x0, finish
    ldr s0, [x0, #0x18]
    fcvtzu w22, s0
    mov x0, x19
    bl {GET_USER_GEMS:#x}
    cmp w0, w22
    b.hs pay
    str w22, [sp, #0x50]
    str wzr, [sp, #0x54]
    str xzr, [sp, #0x58]
    str xzr, [sp, #0x60]
    adrp x0, {IAP_MANAGER_GOT & ~0xfff:#x}
    ldr x0, [x0, #{IAP_MANAGER_GOT & 0xfff:#x}]
    ldr x0, [x0]
    cbz x0, report
    add x1, sp, #0x50
    bl {NOT_ENOUGH_GEMS:#x}
    b report
pay:
    mov x0, x19
    neg w1, w22
    bl {CREDIT_GEMS:#x}
    ldr x23, [x20, #0x10]
    cbz x23, paid
    mov w24, #0
next_item:
    ldr w0, [x23]
    cmp w24, w0
    b.hs paid
    ldr x0, [x23, #8]
    mov w1, #0x30
    umull x1, w24, w1
    add x1, x0, x1
    ldr w0, [x1]
    ldr w22, [x1, #0x28]
    bl {GET_OLD_ITEM_ID:#x}
    mov w1, w0
    mov w2, w22
    mov x0, x19
    bl {CREDIT_ITEM:#x}
    add w24, w24, #1
    b next_item
paid:
    mov w21, #0
report:
    str w21, [sp, #0x40]
    str x20, [sp, #0x48]
    mov w0, #2
    str w0, [x19, #0x37c]
    mov x0, x19
    add x1, sp, #0x40
    bl {ON_BUY_RESULT:#x}
finish:
    mov w0, #2
    ldp x23, x24, [sp, #0x30]
    ldp x21, x22, [sp, #0x20]
    ldp x19, x20, [sp, #0x10]
    ldp x29, x30, [sp], #0x70
    ret
"""
    cave = bytes(ks.asm(src, CAVE)[0])
    assert data[FMT_S_S:FMT_S_S + 5] == b"%s%s\0"

    # generateBarredPrice with a single token (runs in that function's frame)
    barred_at = (CAVE + len(cave) + 0xF) & ~0xF
    barred = bytes(ks.asm(f"""
    ldr x0, [sp, #0x90]
    cmp w0, #2
    b.lo one_token
    b {BARRED_RESUME:#x}
one_token:
    add x25, sp, #0x148
    mov x0, x25
    bl {STRING8_CTOR:#x}
    adrp x4, {EMPTY_CSTR_GOT & ~0xfff:#x}
    ldr x4, [x4, #{EMPTY_CSTR_GOT & 0xfff:#x}]
    ldr x2, [sp, #0xd8]
    cmp x2, #0
    csel x2, x4, x2, eq
    mov x3, x4
    ldr w0, [sp, #0x90]
    cbz w0, format
    ldr x1, [sp, #0x98]
    ldr x3, [x1, #0x10]
    cmp x3, #0
    csel x3, x4, x3, eq
format:
    mov x0, x25
    adrp x1, {FMT_S_S & ~0xfff:#x}
    add x1, x1, #{FMT_S_S & 0xfff:#x}
    bl {SET_TEXT_FORMAT:#x}
    b {BARRED_DONE:#x}
""", barred_at)[0])
    assert barred_at + len(barred) <= CAVE_END
    return {CAVE: cave, barred_at: barred,
            BARRED: bytes(ks.asm(f"b {barred_at:#x}", BARRED)[0]),
            CTOR_BUY: bytes(ks.asm("ret", CTOR_BUY)[0]),
            UPDATE: bytes(ks.asm(f"b {CAVE:#x}", UPDATE)[0]),
            NO_GEM_PACK: bytes(ks.asm(f"""
                mov x0, x19
                mov w1, #{NOT_ENOUGH_GEMS_TEXT:#x}
                bl {OPEN_INFOTEXT:#x}
                b {NO_GEM_PACK_DONE:#x}
            """, NO_GEM_PACK)[0])}
