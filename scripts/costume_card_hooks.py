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
    again at every frame of updateCurrentEventScreen (hook FRAME_HOOK, x26 = the manager);
  - the costume's own picture instead: an actor of dynamiccostumesendless.tpl (the costume icons of
    the costume shop's packs, one animation per costume named by the costume's StringID, event
    costumes included) is spawned on the card and given the costume's animation (icon_source).
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

# --- the costume's own icon on the card (spawned actor, see icon_source) ---
ICON_AT = CAVE + 0x600          # icon routines (the main hook and the frame hook take less)
ICON_STATE = 0x253AF00          # ObjectRef of the spawned icon: unused end of the last .bss page
                                # (the RW segment ends at 0x253a6d8, its page is mapped up to 0x253b000)
ICON_TEMPLATE = b"world/common/ui/common/dynamicpackcostume/dynamiccostumes/dynamiccostumesendless.tpl\0"
SPAWN_INFO_CTOR = 0x10EF650     # SpawnActorInfo::SpawnActorInfo()
SPAWN_INFO_DTOR = 0xEA90BC      # SpawnActorInfo::~SpawnActorInfo()
PATH_CTOR_CSTR = 0xC96884       # Path::Path(const char*, u32)
PATH_ASSIGN = 0x18B3094         # Path::operator=(const Path&)
PATH_DTOR = 0xC7BC50            # Path::~Path()
GET_POS = 0xE9FE70              # Pickable::getPos() -> Vec3d (x8)
GET_WORLD = 0xE9F530            # Pickable::getWorld()
GET_ROOT_SCENE = 0xEA5468       # World::getRootScene()
WORLD_MANAGER_GOT = 0x24B1E38   # -> WorldManager*
SPAWN_ACTOR = 0xECB80C          # WorldManager::spawnActor(SpawnActorInfo&) -> Actor*
GET_ACTOR = 0xD5035C            # ActorRef::getActor()
CREATE_PARENT_BIND = 0xEDF15C   # Actor::createParentBind(bool, Actor* parent, Bind::Type, u32, bool, bool, bool, bool)
GET_UI_COMPONENT = 0xF75E3C     # Actor::GetComponent<UIComponent>()
GET_UI_MASK = 0x10B2180         # UIComponent::getUIDisplayMask()
SET_UI_MASK = 0x10C5ADC         # UIComponent::setUIDisplayMask(View::MaskIds, bool)
GET_ANIM_LIGHT = 0xCB6DEC       # Actor::GetComponent<AnimLightComponent>()
GET_SCALE = 0xEA00C8            # Pickable::getScale() -> Vec2d (s0, s1)
SET_SCALE = 0xEC9E94            # Pickable::setScale(const Vec2d&)


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
    mov x0, x22
    mov w1, w24
    mov w2, #1
    bl {ICON_AT:#x}
    b done
show_visuals:
{_for_visuals(SHOW, 'show')}
    bl icon_hide_entry
done:
    ldr x20, [x20, #0xd00]
    b {HOOK_RETURN:#x}
"""
    src = src.replace("bl icon_hide_entry", f"bl {ICON_AT + 4:#x}")
    cave = bytes(ks.asm(src, CAVE)[0])
    assert CAVE + len(cave) <= ICON_AT

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
    mov w21, w0
{frame_native}
    ldr x0, [x26, #0x118]
    {_movw('w1', COSTUME_BUTTON)}
    mov w2, #1
    bl {GET_CHILD_ACTOR:#x}
    cbz x0, frame_out
    mov x22, x0
{_for_visuals(HIDE, 'frame_hide')}
    mov x0, x22
    mov w1, w21
    mov w2, #0
    bl {ICON_AT:#x}
frame_out:
    ldp x21, x22, [sp, #0x20]
    ldp x19, x20, [sp, #0x10]
    ldp x29, x30, [sp], #0x30
    ldr x0, [x26, #0x118]
    b {FRAME_HOOK_RETURN:#x}
"""
    frame = bytes(ks.asm(frame_src, frame_at)[0])
    assert frame_at + len(frame) <= ICON_AT
    icon = bytes(ks.asm(icon_source(), ICON_AT)[0])
    assert ICON_AT + len(icon) <= CAVE_END
    return {CAVE: cave, frame_at: frame, ICON_AT: icon,
            HOOK: bytes(ks.asm(f"b {CAVE:#x}", HOOK)[0]),
            FRAME_HOOK: bytes(ks.asm(f"b {frame_at:#x}", FRAME_HOOK)[0])}


def icon_source():
    """icon_show(x0 = card "costumeButton", w1 = costume, w2 = set the animation) at ICON_AT,
    icon_hide() at ICON_AT + 4.

    The card's picture only exists for the built-in costume. The special packs of the shop show a
    costume with an icon actor (dynamicpackslotitem.tsc "iconCostume", RLC_InAppPurchaseManager::
    updateDynamicPackSlot: AnimLightComponent, vtable +0x1e8 setAnim). dynamiccostumesendless.tpl has
    the icons of the 76 costumes, event costumes included, each animation named by the costume's
    StringID (getDynamicSlotCostumeIconAnimationID gives the names of the smaller dynamiccostumes.tpl,
    wrong for event costumes: "raymanraybolt" for Rayman_Spaceray).

    WorldManager::spawnActor (as RLC_GS_Leaderboard::spawnPath) creates it in the card's scene at the
    card's position; it loads asynchronously, so on the next calls (every frame of the event screen)
    once loaded (+0x10 bit 7 and +0x258 bit 3, as ActorSpawner::checkReadyAndRegister): bound to the
    card (Actor::createParentBind, as RO2_UIItemCompetitorsComponent does for its flags; binding it
    earlier left a child without bind and crashed BindHandler::update) with the card's UI display mask,
    1.5 times bigger (the icons are drawn for the pack slots), then setAnim and AIUtils::show. Its
    ObjectRef is kept in ICON_STATE, so it is spawned again when the screen's scene is gone.
    """
    s_info = 0x50                   # SpawnActorInfo (0xe8 bytes): +0x20 pos, +0x38 path, +0xa0 scene, +0xe0 flags
    tmp_path = 0x140
    return f"""
    b icon_show
    b icon_hide
icon_hide:
    stp x29, x30, [sp, #-0x20]!
    mov x29, sp
    adrp x0, {ICON_STATE & ~0xfff:#x}
    add x0, x0, #{ICON_STATE & 0xfff:#x}
    ldr w1, [x0]
    cbz w1, hide_out
    bl {GET_ACTOR:#x}
    cbz x0, hide_out
    fmov s0, wzr
    bl {HIDE:#x}
hide_out:
    ldp x29, x30, [sp], #0x20
    ret

icon_show:
    sub sp, sp, #0x180
    stp x29, x30, [sp, #0x10]
    add x29, sp, #0x10
    stp x19, x20, [sp, #0x20]
    stp x21, x22, [sp, #0x30]
    mov x19, x0
    mov w20, w1
    str w2, [sp, #0x48]
    adrp x21, {ICON_STATE & ~0xfff:#x}
    add x21, x21, #{ICON_STATE & 0xfff:#x}
    ldr w9, [x21]
    cbz w9, spawn
    mov x0, x21
    bl {GET_ACTOR:#x}
    mov x22, x0
    cbnz x0, ready
spawn:
    add x0, sp, #{s_info:#x}
    bl {SPAWN_INFO_CTOR:#x}
    add x0, sp, #{tmp_path:#x}
    adr x1, icon_template
    mov w2, #0
    bl {PATH_CTOR_CSTR:#x}
    add x0, sp, #{s_info + 0x38:#x}
    add x1, sp, #{tmp_path:#x}
    bl {PATH_ASSIGN:#x}
    add x0, sp, #{tmp_path:#x}
    bl {PATH_DTOR:#x}
    mov x0, x19
    add x8, sp, #0x40
    bl {GET_POS:#x}
    ldr w9, [sp, #0x40]
    str w9, [sp, #{s_info + 0x20:#x}]
    ldr w9, [sp, #0x44]
    str w9, [sp, #{s_info + 0x24:#x}]
    ldr w9, [sp, #0x48]
    str w9, [sp, #{s_info + 0x28:#x}]
    ldrb w9, [sp, #{s_info + 0xe0:#x}]
    orr w9, w9, #4
    strb w9, [sp, #{s_info + 0xe0:#x}]
    mov x0, x19
    bl {GET_WORLD:#x}
    mov x22, #0
    cbz x0, spawned
    bl {GET_ROOT_SCENE:#x}
    cbz x0, spawned
    ldr w9, [x0, #8]
    str w9, [sp, #{s_info + 0xa0:#x}]
    adrp x0, {WORLD_MANAGER_GOT & ~0xfff:#x}
    ldr x0, [x0, #{WORLD_MANAGER_GOT & 0xfff:#x}]
    ldr x0, [x0]
    add x1, sp, #{s_info:#x}
    bl {SPAWN_ACTOR:#x}
    mov x22, x0
spawned:
    add x0, sp, #{s_info:#x}
    bl {SPAWN_INFO_DTOR:#x}
    cbz x22, show_out
    ldr w9, [x22, #8]
    str w9, [x21]
    b show_out                      // loads asynchronously: bound on a later frame
ready:
    ldrb w9, [x22, #0x10]           // loaded: +0x10 bit 7 and +0x258 bit 3 (ActorSpawner::checkReadyAndRegister)
    tbz w9, #7, show_out
    ldrb w9, [x22, #0x258]
    tbz w9, #3, show_out
    ldr x9, [x22, #0x290]           // not bound yet: bind it, then set its animation
    cbz x9, bind
    ldr w9, [sp, #0x48]
    cbz w9, show_icon
    b have
bind:
    strb wzr, [sp]
    mov x0, x22
    mov w1, #0
    mov x2, x19
    mov w3, #0
    mov w4, #0
    mov w5, #1
    mov w6, #0
    mov w7, #0
    bl {CREATE_PARENT_BIND:#x}
    ldr x9, [x22, #0x290]
    cbz x9, mask
    str xzr, [x9, #0x5c]
    str wzr, [x9, #0x64]
    str xzr, [x9, #0x68]
    str wzr, [x9, #0x70]
    mov w10, #1
    strb w10, [x9, #0x48]
mask:
    mov x0, x19
    bl {GET_UI_COMPONENT:#x}
    mov x21, x0
    mov x0, x22
    bl {GET_UI_COMPONENT:#x}
    cbz x0, scale
    cbz x21, scale
    str x0, [sp, #0x40]
    mov x0, x21
    bl {GET_UI_MASK:#x}
    mov w1, w0
    mov w2, #1
    ldr x0, [sp, #0x40]
    bl {SET_UI_MASK:#x}
scale:
    mov x0, x22                     // the icons are drawn for the smaller pack slots: 1.5 times bigger
    bl {GET_SCALE:#x}
    fmov s2, #1.5
    fmul s0, s0, s2
    fmul s1, s1, s2
    str s0, [sp, #0x40]
    str s1, [sp, #0x44]
    mov x0, x22
    add x1, sp, #0x40
    bl {SET_SCALE:#x}
have:
    mov x0, x22
    bl {GET_ANIM_LIGHT:#x}
    cbz x0, show_icon
    mov x21, x0
    str w20, [sp, #0x44]            // dynamiccostumesendless.tpl: one animation per costume, named by its StringID
    ldr x9, [x21]
    ldr x9, [x9, #0x1e8]
    mov x0, x21
    add x1, sp, #0x44
    mov w2, #-1
    mov w3, #0
    mov w4, #0
    blr x9
show_icon:
    mov x0, x22
    fmov s0, wzr
    bl {SHOW:#x}
show_out:
    ldp x21, x22, [sp, #0x30]
    ldp x19, x20, [sp, #0x20]
    ldp x29, x30, [sp, #0x10]
    add sp, sp, #0x180
    ret
icon_template:
    .byte {", ".join(str(c) for c in ICON_TEMPLATE)}
"""
