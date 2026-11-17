"""Incubator synchronisation between libuaf.so and the embedded game server.

The original game kept the incubated egg on Ubisoft's server; every incubationStatus answer is
authoritative on the client (RLC_Incubator::onGameServerRequestDone):
  - server egg id == "no creature"  -> flushIncubator(): the local egg is deleted
  - server egg id != local egg id    -> the local egg is replaced by the server's
  - HTTP 404                         -> flushIncubator()
  - other HTTP 4xx                   -> answer ignored, local egg kept

Fixes applied here (the startIncubation / "hatch now" routing is in build_libuaf_offline.py):

1. (removed 16/11/2026) 0x17c2a4c, RLC_Incubator::updateMenuElixir, tap on a ready egg: the original
   code hatches locally during onboarding (isOnBoarding) and asks the server afterwards. Forcing the
   server path broke the tutorial: the game server is not connected yet during onboarding (no
   request reaches it) and the egg could not be used. The original test is kept; a local tutorial
   egg unknown to the server is handled by 2. once onboarding is over.

2. 0x17b9b2c, RLC_Incubator::onGameServerRequestDone, IncubationStatus failure branch: the
   embedded server answers HTTP 410 ("unknown egg") instead of an empty incubator when it has no
   egg, so eggs incubated locally by older builds are no longer deleted. When that 410 answers an
   autoHatch request (byte this+0xec, set by askIncubationStatus), the client hatches its local
   egg itself, as those builds did.

3. 0x175c3c8, RLC_Incubator::askIncubationStatus: an autoHatch request for a local egg was sent
   as a blocking request (RequestType 2), whose failures pop up "Une erreur est survenue sur nos
   serveurs" - including the 410 above. Always send it as a background request (RequestType 1).
   (HTTP 409 is not usable for 2.: the game server layer reads it as "newer save on the server".)

4. 0x17b9864, RLC_Incubator::onGameServerRequestDone, IncubationStatus success: when the server's
   egg differs from the local one, the client replaced its egg with the server's. But the
   silver / gold / new-creature elixirs re-roll the egg on the client (requestAsyncElixir ->
   RLC_CreatureManager::HatchSimulation, made local by the legacy patch at 0x16b2e04) and never
   tell the server, so the hatch turned the re-rolled egg back into the original one ("common").
   Now the server's egg is only taken when the client has no egg.
"""

CAVE = 0xE0AF00          # end of the zero run used by net_hooks (0xe0a080) / debug_hooks (0xe0a200)
CAVE_END = 0xE0B050

STATUS_FAIL = 0x17b9b2c          # cmp w0, #0x1f3 ; b.ls 0x17b9ad4
STATUS_FAIL_ORIG = "1fcc077129fdff54"
STATUS_DONE = 0x17b9ad4          # common exit of the IncubationStatus branch
STATUS_5XX = 0x17b9b34           # original code for 5xx errors
PICK_EGG = 0x1733ec4             # RLC_Incubator::pickEggFromIncubator(this)
STATUS_REQ_TYPE = 0x175c3c8      # eor w2, w2, #1   (w2: 1 = background request, 0 = blocking)
STATUS_REQ_TYPE_ORIG = "42000052"
EGG_COMPARE = 0x17b9864          # cmp w23, w0 ; b.eq 0x17b98d0   (w23 = server egg, w0 = local egg)
EGG_COMPARE_ORIG = "ff02006b40030054"
EGG_KEEP_LOCAL = 0x17b98d0       # skip the overwrite
EGG_ADOPT_SERVER = 0x17b986c     # build the local egg from the server's
INVALID_STRINGID_GOT = 0x24be958 # GOT slot -> ITF::StringID::Invalid
HTTP_UNKNOWN_EGG = 410


def assemble(data):
    import keystone
    ks = keystone.Ks(keystone.KS_ARCH_ARM64, keystone.KS_MODE_LITTLE_ENDIAN)
    assert data[STATUS_FAIL:STATUS_FAIL + 8].hex() == STATUS_FAIL_ORIG, "unexpected bytes (status failure)"
    assert data[STATUS_REQ_TYPE:STATUS_REQ_TYPE + 4].hex() == STATUS_REQ_TYPE_ORIG, "unexpected bytes (request type)"
    assert data[EGG_COMPARE:EGG_COMPARE + 8].hex() == EGG_COMPARE_ORIG, "unexpected bytes (egg compare)"
    # x19 = this (RLC_Incubator), w0 = HTTP status of the IncubationStatus answer
    cave = bytes(ks.asm(f"""
        cmp w0, #{HTTP_UNKNOWN_EGG}
        b.ne not_unknown
        ldrb w1, [x19, #0xec]
        cbz w1, done
        mov x0, x19
        bl {PICK_EGG:#x}
    done:
        b {STATUS_DONE:#x}
    not_unknown:
        cmp w0, #0x1f3
        b.hi is_5xx
        b {STATUS_DONE:#x}
    is_5xx:
        b {STATUS_5XX:#x}
    """, CAVE)[0])
    egg_cave = CAVE + len(cave)
    cave += bytes(ks.asm(f"""
        cmp w23, w0
        b.eq keep_local
        adrp x1, {INVALID_STRINGID_GOT & ~0xfff:#x}
        ldr x1, [x1, #{INVALID_STRINGID_GOT & 0xfff:#x}]
        ldr w1, [x1]
        cmp w0, w1
        b.ne keep_local
        b {EGG_ADOPT_SERVER:#x}
    keep_local:
        b {EGG_KEEP_LOCAL:#x}
    """, egg_cave)[0])
    assert CAVE + len(cave) <= CAVE_END
    # conditional branches only reach +-1 MB: every far target above must be an unconditional "b"
    import capstone
    md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)
    for i in md.disasm(cave, CAVE):
        if i.mnemonic.startswith(("b.", "cbz", "cbnz")):
            assert CAVE <= int(i.op_str.split("#")[-1], 16) < CAVE_END, f"far conditional branch: {i}"
    return {
        CAVE: cave,
        STATUS_FAIL: bytes(ks.asm(f"b {CAVE:#x}", STATUS_FAIL)[0]),
        STATUS_REQ_TYPE: bytes(ks.asm("mov w2, #1", STATUS_REQ_TYPE)[0]),
        EGG_COMPARE: bytes(ks.asm(f"b {egg_cave:#x}; nop", EGG_COMPARE)[0]),
    }


if __name__ == "__main__":
    import capstone, os
    lib = os.path.join(os.path.dirname(__file__), "..", "binaries", "libuaf_original.so")
    md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)
    for a, b in assemble(open(lib, "rb").read()).items():
        print(f"; {a:#x}")
        for i in md.disasm(b, a):
            print(f"  {i.address:#x}: {i.mnemonic} {i.op_str}")
