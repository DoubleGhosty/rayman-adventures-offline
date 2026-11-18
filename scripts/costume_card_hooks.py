"""Seasonal event shop: the costume card shows the costume that is really sold.

The game ships the look of only the last event of each type (hunt 9 Raybarbe, wheel 17 Rayhistorik,
marathon 16 Raystidigitateur) and every event id of that type reuses it. The costume sold, though,
depends on the id (RLC_SeasonalEventManager::getCurrentSeasonalEventCostume: Teensy_Bunny for 1,
Globox_Halloween for 3, Rayman_Spaceray for 13...), and buying it equips it. The costume card kept
the title and picture of the last event's costume, written in the screen data (menuhuntevent.isc,
menuchallengewheelevent.isc, endlessrunnerevent/eventmenu.isc): "RAYBARBE" could sell a Teensy.

Hook at the end of refreshCurrentEventScreenCostume (called when the event screen opens and after a
purchase; x23 = the manager, w24 = the costume's StringID, [x23+0x118] = the screen's UIComponent):
  - title: node "pack3Name" -> UITextBox -> setLocId (vtable +0x1c8, as the function does for its
    "Buy"/"Equip" text) with RLC_InAppPurchaseManager::getCostumeNameId(costume), the costume's own
    name (the one the costume shop shows);
  - picture: the card's "*visuals" actor (bound to "costumeButton") only holds the last event's
    costume art. It is hidden (AIUtils::hide = EventShow alpha 0) when the costume is another one. The
    menu's own show transition shows its children again after the refresh, so the picture is hidden
    again at every frame of updateCurrentEventScreen (hook FRAME_HOOK, x26 = the manager).
"""

CAVE = 0xEF8300             # zero run 0xef82fc..0xef92f0, nothing branches into it
CAVE_END = 0xEF92F0
HOOK = 0x1772FA8            # "ldr x20, [x20, #0xd00]" (epilogue of refreshCurrentEventScreenCostume)
HOOK_ORIG = "948246f9"
HOOK_RETURN = 0x1772FAC
FRAME_HOOK = 0x17C5CF8      # "ldr x0, [x26, #0x118]" at the start of updateCurrentEventScreen
FRAME_HOOK_ORIG = "408f40f9"
FRAME_HOOK_RETURN = 0x17C5CFC
GET_EVENT_COSTUME = 0x17405AC   # RLC_SeasonalEventManager::getCurrentSeasonalEventCostume() const

GET_CHILD_ACTOR = 0x10B1FB0     # UIComponent::getChildActor(StringID, bool recursive): UI items
ACTOR_GET_CHILD = 0xEDEF70      # Actor::getChildActor(StringID, bool recursive): actors bound to an actor
GET_TEXTBOX = 0xD6D5E4          # Actor::GetComponent<UITextBox>
GET_COSTUME_NAME_ID = 0x1645C84 # RLC_InAppPurchaseManager::getCostumeNameId(StringID) (ignores this)
HIDE = 0xF768C4                 # AIUtils::hide(Actor*, float)
SHOW = 0xF76684                 # AIUtils::show(Actor*, float)

PACK3_NAME = 0xA0645C0F         # stringid("pack3Name")
COSTUME_BUTTON = 0xDA910B86     # stringid("costumeButton"), the card
VISUALS = (0x1D63E944, 0xD59F0E63, 0x543C0289)  # hunteventvisuals, challengewheelvisuals, endlessrunnereventvisuals
NATIVE_COSTUMES = (0x501BC26C, 0xC8A86CCB, 0xCA937490)  # Rayman_Raybeard (9), Barbara_IceAge (17), Rayman_Raywiz (16)


def _movw(reg, value):
    return f"mov {reg}, #{value & 0xffff:#x}\n    movk {reg}, #{value >> 16:#x}, lsl #16"


def _for_visuals(func, label):
    """Call func(visual actor, 0.0) on each "*visuals" actor bound to the card (x22)."""
    return "\n".join(f"""    mov x0, x22
    {_movw('w1', v)}
    mov w2, #1
    bl {ACTOR_GET_CHILD:#x}
    cbz x0, {label}_{i}
    fmov s0, wzr
    bl {func:#x}
{label}_{i}:""" for i, v in enumerate(VISUALS))


def assemble(data):
    import keystone
    ks = keystone.Ks(keystone.KS_ARCH_ARM64, keystone.KS_MODE_LITTLE_ENDIAN)
    got = data[HOOK:HOOK + 4].hex()
    assert got == HOOK_ORIG, f"unexpected bytes at {HOOK:#x}: {got}"
    assert data[CAVE:CAVE_END] == bytes(CAVE_END - CAVE), "costume card cave not empty"

    native = "\n".join(f"    {_movw('w1', c)}\n    cmp w24, w1\n    b.eq show_visuals" for c in NATIVE_COSTUMES)
    src = f"""
    ldr x0, [x23, #0x118]
    cbz x0, done
    {_movw('w1', PACK3_NAME)}
    mov w2, #1
    bl {GET_CHILD_ACTOR:#x}
    cbz x0, picture
    bl {GET_TEXTBOX:#x}
    cbz x0, picture
    mov x21, x0
    mov w1, w24
    bl {GET_COSTUME_NAME_ID:#x}
    cmn w0, #1
    b.eq picture
    str w0, [sp, #0x58]
    ldr x2, [x21]
    ldr x2, [x2, #0x1c8]
    mov x0, x21
    add x1, sp, #0x58
    blr x2
picture:
    ldr x0, [x23, #0x118]
    {_movw('w1', COSTUME_BUTTON)}
    mov w2, #1
    bl {GET_CHILD_ACTOR:#x}
    cbz x0, done
    mov x22, x0
{native}
{_for_visuals(HIDE, 'hide')}
    b done
show_visuals:
{_for_visuals(SHOW, 'show')}
done:
    ldr x20, [x20, #0xd00]
    b {HOOK_RETURN:#x}
"""
    cave = bytes(ks.asm(src, CAVE)[0])

    # every frame of updateCurrentEventScreen: hide the picture again (x26 = manager, x19 must survive)
    got = data[FRAME_HOOK:FRAME_HOOK + 4].hex()
    assert got == FRAME_HOOK_ORIG, f"unexpected bytes at {FRAME_HOOK:#x}: {got}"
    frame_native = "\n".join(f"    {_movw('w1', c)}\n    cmp w0, w1\n    b.eq frame_out" for c in NATIVE_COSTUMES)
    frame_at = (CAVE + len(cave) + 0xF) & ~0xF
    frame_src = f"""
    stp x29, x30, [sp, #-0x30]!
    stp x19, x20, [sp, #0x10]
    stp x21, x22, [sp, #0x20]
    ldr x0, [x26, #0x118]
    cbz x0, frame_out
    mov x0, x26
    bl {GET_EVENT_COSTUME:#x}
{frame_native}
    ldr x0, [x26, #0x118]
    {_movw('w1', COSTUME_BUTTON)}
    mov w2, #1
    bl {GET_CHILD_ACTOR:#x}
    cbz x0, frame_out
    mov x22, x0
{_for_visuals(HIDE, 'frame_hide')}
frame_out:
    ldp x21, x22, [sp, #0x20]
    ldp x19, x20, [sp, #0x10]
    ldp x29, x30, [sp], #0x30
    ldr x0, [x26, #0x118]
    b {FRAME_HOOK_RETURN:#x}
"""
    frame = bytes(ks.asm(frame_src, frame_at)[0])
    assert frame_at + len(frame) <= CAVE_END
    return {CAVE: cave, frame_at: frame,
            HOOK: bytes(ks.asm(f"b {CAVE:#x}", HOOK)[0]),
            FRAME_HOOK: bytes(ks.asm(f"b {frame_at:#x}", FRAME_HOOK)[0])}
