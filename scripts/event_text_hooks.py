"""Seasonal event texts that name the costume: the costume really sold.

The game only ships the look of the last event of each type (costume_card_hooks.py), and its texts
too: the event intro popup says "Echange des Doubloons contre le nouveau costume de Raybarbe..."
(text 0x9ac, hunts), "...contre le nouveau costume de Barbarrrrr..." (0x932, spin wheels) or
"...contre le nouveau costume de Raystidigitateur..." (0x969, marathons) whatever the event, while
the shop sells another costume (RLC_SeasonalEventManager::getCurrentSeasonalEventCostume).

Hook at the entry of ITF::Localisation_Template::getText(LocalisationId const&, ITF_LANGUAGE, bool*,
BaseObject*) (0xe95204, String8 returned through x8), which every text box goes through
(UITextBox::setLoc, SmartLocId::getText, LocalisationManager::getText...). For those three texts the
cave calls the original, then, when the current event's costume is not the built-in one, replaces the
built-in costume's name (texts 0x9d4 "Raybarbe", 0xb29 "Barbarrrrr", 0xae2 "Raystidigitateur", in the
same language) by the name of the costume sold (RLC_InAppPurchaseManager::getCostumeNameId, the name
the costume shop shows) with ITF::String8::replace.
"""

CAVE = 0xFDC400             # zero run after pack_purchase_hooks.py (0xfdc200..0xfdc360), up to 0xfdd0f8
CAVE_END = 0xFDD0F8
HOOK = 0xE95204             # Localisation_Template::getText, "sub sp, sp, #0xf0"
HOOK_ORIG = "ffc303d1"
HOOK_RETURN = 0xE95208

GET_EVENT_COSTUME = 0x17405AC   # RLC_SeasonalEventManager::getCurrentSeasonalEventCostume() const
EVENT_MANAGER = 0x25138F0       # RLC_SeasonalEventManager::s_instance
GET_COSTUME_NAME_ID = 0x1645C84 # RLC_InAppPurchaseManager::getCostumeNameId(StringID) (ignores this)
STRING8_REPLACE = 0x18B591C     # ITF::String8::replace(const char*, const char*)
STRING8_DTOR = 0xC7A334         # ITF::String8::~String8()

# text id -> (built-in costume StringID, text id of that costume's name)
TEXTS = {
    0x9AC: (0x501BC26C, 0x9D4),     # hunts: Rayman_Raybeard, "Raybarbe"
    0x932: (0xC8A86CCB, 0xB29),     # spin wheels: Barbara_IceAge, "Barbarrrrr"
    0x969: (0xCA937490, 0xAE2),     # marathons: Rayman_Raywiz, "Raystidigitateur"
}


def _movw(reg, value):
    return f"mov {reg}, #{value & 0xffff:#x}\n    movk {reg}, #{value >> 16:#x}, lsl #16"


def assemble(data):
    import keystone
    ks = keystone.Ks(keystone.KS_ARCH_ARM64, keystone.KS_MODE_LITTLE_ENDIAN)
    got = data[HOOK:HOOK + 4].hex()
    assert got == HOOK_ORIG, f"unexpected bytes at {HOOK:#x}: {got}"
    assert data[CAVE:CAVE_END] == bytes(CAVE_END - CAVE), "event text cave not empty"

    checks = "\n".join(f"    mov w10, #{t:#x}\n    cmp w9, w10\n    b.eq wrap" for t in TEXTS)
    picks = "\n".join(f"""    mov w10, #{t:#x}
    cmp w21, w10
    b.ne not_{i}
    {_movw('w25', costume)}
    mov w26, #{name:#x}
not_{i}:""" for i, (t, (costume, name)) in enumerate(TEXTS.items()))
    src = f"""
    ldr w9, [x1]
{checks}
original:
    sub sp, sp, #0xf0
    b {HOOK_RETURN:#x}
wrap:
    stp x29, x30, [sp, #-0xa0]!
    mov x29, sp
    stp x19, x20, [sp, #0x10]
    stp x21, x22, [sp, #0x20]
    stp x23, x24, [sp, #0x30]
    stp x25, x26, [sp, #0x40]
    mov x19, x8
    mov x20, x0
    mov w21, w9
    mov w22, w2
    bl original
{picks}
    adrp x0, {EVENT_MANAGER & ~0xfff:#x}
    ldr x0, [x0, #{EVENT_MANAGER & 0xfff:#x}]
    cbz x0, done
    bl {GET_EVENT_COSTUME:#x}
    cbz w0, done
    cmn w0, #1
    b.eq done
    cmp w0, w25
    b.eq done
    mov w1, w0
    bl {GET_COSTUME_NAME_ID:#x}
    cmn w0, #1
    b.eq done
    str w0, [sp, #0x50]
    str w26, [sp, #0x54]
    mov x0, x20
    add x1, sp, #0x50
    mov w2, w22
    mov x3, #0
    mov x4, #0
    add x8, sp, #0x60
    bl {HOOK:#x}
    mov x0, x20
    add x1, sp, #0x54
    mov w2, w22
    mov x3, #0
    mov x4, #0
    add x8, sp, #0x80
    bl {HOOK:#x}
    ldr x1, [sp, #0x90]
    ldr x2, [sp, #0x70]
    cbz x1, free
    cbz x2, free
    ldrb w9, [x1]
    cbz w9, free
    mov x0, x19
    bl {STRING8_REPLACE:#x}
free:
    add x0, sp, #0x60
    bl {STRING8_DTOR:#x}
    add x0, sp, #0x80
    bl {STRING8_DTOR:#x}
done:
    mov x0, x19
    ldp x25, x26, [sp, #0x40]
    ldp x23, x24, [sp, #0x30]
    ldp x21, x22, [sp, #0x20]
    ldp x19, x20, [sp, #0x10]
    ldp x29, x30, [sp], #0xa0
    ret
"""
    cave = bytes(ks.asm(src, CAVE)[0])
    assert CAVE + len(cave) <= CAVE_END
    return {CAVE: cave, HOOK: bytes(ks.asm(f"b {CAVE:#x}", HOOK)[0])}
