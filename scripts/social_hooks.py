"""No more Facebook "Play with friends!" popup.

RLC_SocialManager::openMenuFacebookBenefits opens the "PLAY WITH FRIENDS! / Save your progress /
Exclusive Raybox costume! 500 <event currency> / CONNECT" menu, which asks for a Facebook login that
can never work offline (the Ray-box is sold for 1 gem in the costume shop, costume_unlock_hooks.py).
It is opened from the adventure map's start (RLC_GS_AdventureMap::updateGSAdventureInitPhase), the
social incentive and shop pack checks of RLC_SocialManager, and once per seasonal event by
RLC_SeasonalEventManager::tryShowFacebookBenefitsPopup (while the Facebook costume is locked).

  - openMenuFacebookBenefits (0x17bc988, void): returns at once;
  - tryShowFacebookBenefitsPopup (0x17bcf8c): returns false ("not shown"), so that
    checkDisplaySeasonalPopupInfo goes on with the event's own popups.
"""

OPEN_MENU = 0x17BC988           # RLC_SocialManager::openMenuFacebookBenefits(bool), "sub sp, sp, #0x1d0"
OPEN_MENU_ORIG = "ff4307d1"
TRY_SHOW = 0x17BCF8C            # RLC_SeasonalEventManager::tryShowFacebookBenefitsPopup(), "sub sp, sp, #0x30"
TRY_SHOW_ORIG = "ffc300d1f55b01a9"


def assemble(data):
    import keystone
    ks = keystone.Ks(keystone.KS_ARCH_ARM64, keystone.KS_MODE_LITTLE_ENDIAN)
    for addr, orig in ((OPEN_MENU, OPEN_MENU_ORIG), (TRY_SHOW, TRY_SHOW_ORIG)):
        got = data[addr:addr + len(orig) // 2].hex()
        assert got == orig, f"unexpected bytes at {addr:#x}: {got}"
    return {OPEN_MENU: bytes(ks.asm("ret", OPEN_MENU)[0]),
            TRY_SHOW: bytes(ks.asm("mov w0, #0\nret", TRY_SHOW)[0])}
