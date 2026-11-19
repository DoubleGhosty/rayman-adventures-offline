"""Free currency from the shops' "watch an ad" cards: at most 5 a day for each.

Rewarded videos give their reward at once since the dex patch of GameActivity.playMoPubVideo
(dex_patches.py), so the free "Regarder une publicité" cards of the shops could be tapped without end:
10 gems (gem shop), event currency ("Besoin de plus de ...") and challenge tokens (challenge shop).
They are paid by RLC_InAppPurchaseManager::onVideoRewardedViewed(context): 0 the gem card (it opens
the "3x - watch an ad" offer, whose own video is context 0x12 and stays free), 8 seasonal currency,
9 challenge tokens (other contexts are other objects' listeners: revive, double rewards, wheel
spin... they stay unlimited).

Hook at its entry (0x171b6d4, "sub sp, sp, #0x90"): for those three contexts a counter file
files/rlc/adcap.bin {u32 day (UTC, time()/86400), u32 count[3]} (fopen/fread/fwrite of libc: it
survives restarts) is read; under MAX_PER_DAY the count goes up and the reward is paid as before,
else the game's infotext 0x354 "Plus de publicité disponible pour l'instant. Merci de réessayer plus
tard." is shown (RLC_InAppPurchaseManager::openInfotext) and the reward is skipped. Skipping the whole
function leaves no state behind: its only flag (+0x511, gems multiplier popup) is set inside it.
"""

CAVE = 0xFDC600             # zero run after event_text_hooks.py (0xfdc400..0xfdc564), up to 0xfdd0f8
CAVE_END = 0xFDD0F8
HOOK = 0x171B6D4            # RLC_InAppPurchaseManager::onVideoRewardedViewed(u32), "sub sp, sp, #0x90"
HOOK_ORIG = "ff4302d1"
HOOK_RETURN = 0x171B6D8
MAX_PER_DAY = 5
CONTEXTS = (0, 8, 9)        # gem card, seasonal currency, challenge tokens
NO_AD_TEXT = 0x354
OPEN_INFOTEXT = 0x165D3C4   # RLC_InAppPurchaseManager::openInfotext(u32 text id)
FOPEN, FREAD, FWRITE, FCLOSE, TIME = 0xC6E6D0, 0xC6F720, 0xC6F790, 0xC6F230, 0xC6F890   # libc PLT
COUNTER_FILE = b"/data/data/com.ubisoft.raymanadventures/files/rlc/adcap.bin\0"


def _bytes(data):
    return "    .byte " + ", ".join(str(c) for c in data)


def assemble(data):
    import keystone
    ks = keystone.Ks(keystone.KS_ARCH_ARM64, keystone.KS_MODE_LITTLE_ENDIAN)
    got = data[HOOK:HOOK + 4].hex()
    assert got == HOOK_ORIG, f"unexpected bytes at {HOOK:#x}: {got}"
    assert data[CAVE:CAVE_END] == bytes(CAVE_END - CAVE), "ad cap cave not empty"
    checks = "\n".join(f"    mov w9, #{i}\n    cmp w1, #{c:#x}\n    b.eq capped" for i, c in enumerate(CONTEXTS))
    src = f"""
{checks}
original:
    sub sp, sp, #0x90
    b {HOOK_RETURN:#x}
capped:
    stp x29, x30, [sp, #-0x50]!
    mov x29, sp
    stp x19, x20, [sp, #0x10]
    stp x21, x22, [sp, #0x20]
    mov x19, x0
    mov w20, w1
    mov w21, w9
    stp xzr, xzr, [sp, #0x30]
    adr x0, counter_file
    adr x1, mode_rb
    bl {FOPEN:#x}
    cbz x0, today
    mov x22, x0
    add x0, sp, #0x30
    mov x1, #1
    mov x2, #16
    mov x3, x22
    bl {FREAD:#x}
    mov x0, x22
    bl {FCLOSE:#x}
today:
    mov x0, #0
    bl {TIME:#x}
    mov x9, #0x5180             // 86400
    movk x9, #1, lsl #16
    udiv x0, x0, x9
    ldr w10, [sp, #0x30]
    cmp w10, w0
    b.eq count
    str w0, [sp, #0x30]
    str wzr, [sp, #0x34]
    str xzr, [sp, #0x38]
count:
    add x10, sp, #0x34
    ldr w11, [x10, w21, uxtw #2]
    cmp w11, #{MAX_PER_DAY}
    b.hs over
    add w11, w11, #1
    str w11, [x10, w21, uxtw #2]
    adr x0, counter_file
    adr x1, mode_wb
    bl {FOPEN:#x}
    cbz x0, allowed
    mov x22, x0
    add x0, sp, #0x30
    mov x1, #1
    mov x2, #16
    mov x3, x22
    bl {FWRITE:#x}
    mov x0, x22
    bl {FCLOSE:#x}
allowed:
    mov x0, x19
    mov w1, w20
    ldp x21, x22, [sp, #0x20]
    ldp x19, x20, [sp, #0x10]
    ldp x29, x30, [sp], #0x50
    b original
over:
    mov x0, x19
    mov w1, #{NO_AD_TEXT:#x}
    bl {OPEN_INFOTEXT:#x}
    ldp x21, x22, [sp, #0x20]
    ldp x19, x20, [sp, #0x10]
    ldp x29, x30, [sp], #0x50
    ret
counter_file:
{_bytes(COUNTER_FILE)}
mode_rb:
{_bytes(b"rb" + bytes(1))}
mode_wb:
{_bytes(b"wb" + bytes(1))}
"""
    cave = bytes(ks.asm(src, CAVE)[0])
    assert CAVE + len(cave) <= CAVE_END
    return {CAVE: cave, HOOK: bytes(ks.asm(f"b {CAVE:#x}", HOOK)[0])}
