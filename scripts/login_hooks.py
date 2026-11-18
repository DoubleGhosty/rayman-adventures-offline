"""Title-screen login loop: UbiServices no longer disconnected right after connecting.

UbiServicesModule_SDK::executeSync calls, while its flag +0x4c0 ("SDK to (re)configure") is set, a
routine (0x184efc4) that waits for MobileSDKModule::s_initMSDKDone, then:
  - module disconnected: deletes the ubiservices::Facade, uninitializeSDK / configureSDK, new Facade,
    clears +0x4c0;
  - otherwise: calls Module::disconnect() (vtable +0x28) at every pass until it is disconnected.
Normally the mobile SDK is ready before UbiServices starts connecting, and the first branch runs. When
the game is slow at startup (ad SDKs downloading videos, a busy device), UbiServices is already
connecting: disconnect() does nothing in state 2, then cuts the session as soon as it reaches state 4
(DELETE /v2/profiles/sessions 0.3 s after it was created). The SDK is reconfigured, the module
reconnects 30 s later, and the title screen never sends userprofile/meta (save slots, game globals).
Caught on WSA with the debug hooks (lr of Module::disconnect = 0x184f03c).

Patch: never force the disconnection ("ldr x0, [x19]" at 0x184f02c -> "b <routine end>"). The SDK is
reconfigured the normal way, the next time the module is disconnected; the session that is being
created keeps the Facade that init() configured (same GameConfig / SystemConfig).
"""

FORCE_DISCONNECT = 0x184F02C
FORCE_DISCONNECT_ORIG = "600240f9"     # ldr x0, [x19]
ROUTINE_END = 0x184F214


def assemble(data):
    import keystone
    ks = keystone.Ks(keystone.KS_ARCH_ARM64, keystone.KS_MODE_LITTLE_ENDIAN)
    got = data[FORCE_DISCONNECT:FORCE_DISCONNECT + 4].hex()
    assert got == FORCE_DISCONNECT_ORIG, f"unexpected bytes at {FORCE_DISCONNECT:#x}: {got}"
    return {FORCE_DISCONNECT: bytes(ks.asm(f"b {ROUTINE_END:#x}", FORCE_DISCONNECT)[0])}
