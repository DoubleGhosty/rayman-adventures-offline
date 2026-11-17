"""Lucky ticket egg rewards: pick the creature on the client.

An "Egg" reward (RLC_LuckyTicketReward.type 9) is hatched by RLC_GS_LuckyTicket::
claimShownRewardAndOpenRewardScreen straight from reward.creatureID: Ubisoft's server chose the
creature in its getReward answer. The embedded server only draws the *rarity* (Ubisoft's
ticketEggRarityWeights tables, see offline_server/.../Rewards.java) and sends creatureID = invalid
with the rarity in elixirType0. The game then chooses a creature of that rarity with its own picker,
RLC_CreatureManager::HatchSimulation(acquisition, graphicalFamily, rarity, forceNew) - the same
call (and the same arguments) as the developers' RLC_InventoryManager::DEBUG_generateLuckyTicketReward:
  acquisition: GoldenTicket(4) -> 4, SeasonalTicket(17) -> 8, ChallengeTicket(27) -> 12, else 3
  graphicalFamily: RO2_PersistentGameData_Universe+0x934 (current creature region)

The pick must happen BEFORE the scratch screen is drawn: RLC_GS_LuckyTicket::finishSceneInit colours
the scratched egg symbols with RLC_CreatureManager::getCreatureRarity(reward.creatureID), and an
invalid creature gives rarity 6 (unknown): the ticket showed one egg and the player got a creature
of another rarity (fixed 2026-11-16). So the picker runs at the first egg symbol of the scratch
screen, and again at the claim as a fallback (it does nothing once creatureID is valid).

Hooks (RLC_GS_LuckyTicket: reward at +0xa0 = RLC_LuckyTicketReward {type +0, creatureID +4,
count +0xc, elixirType0 +0x10, ticketType +0x1c}):
  0x169dea0 "ldr w1, [x21, #0xa4]" in finishSceneInit (x21 = RLC_GS_LuckyTicket), egg symbol of an
            egg reward, just before getCreatureRarity; x0 holds an adrp page that is rebuilt.
  0x171a774 "ldr w0, [x19, #0xa0]" in claimShownRewardAndOpenRewardScreen (x19 = RLC_GS_LuckyTicket),
            before the reward screen is opened.
Code in the zero run 0xd6a290.. (free since the legacy isItemOfType cave was dropped).
"""

CAVE = 0xD6A290
CAVE_END = 0xD6B230
CLAIM_HOOK = 0x171a774
CLAIM_ORIG = "60a240b9"   # ldr w0, [x19, #0xa0]
CLAIM_RESUME = 0x171a778
SCRATCH_HOOK = 0x169dea0
SCRATCH_ORIG = "a1a640b9"  # ldr w1, [x21, #0xa4]
SCRATCH_RESUME = 0x169dea4
SCRATCH_X0_PAGE = 0x24a8000  # adrp x0 at 0x169de9c, consumed at 0x169dea4
HATCH_SIMULATION = 0x16922cc
CREATURE_MANAGER_GOT = 0x24a8530
UNIVERSE_GOT = 0x24b1758  # -> ptr -> (+8) RO2_PersistentGameData_Universe


def assemble(data):
    import keystone, capstone
    ks = keystone.Ks(keystone.KS_ARCH_ARM64, keystone.KS_MODE_LITTLE_ENDIAN)
    assert data[CLAIM_HOOK:CLAIM_HOOK + 4].hex() == CLAIM_ORIG, "unexpected bytes (lucky ticket claim)"
    assert data[SCRATCH_HOOK:SCRATCH_HOOK + 4].hex() == SCRATCH_ORIG, "unexpected bytes (lucky ticket scratch)"
    assert data[SCRATCH_HOOK - 4:SCRATCH_HOOK].hex() == bytes(ks.asm(f"adrp x0, {SCRATCH_X0_PAGE:#x}",
                                                                       SCRATCH_HOOK - 4)[0]).hex()
    cave = bytes(ks.asm(f"""
    claim:
        add x0, x19, #0xa0
        bl pick
        ldr w0, [x19, #0xa0]
        b {CLAIM_RESUME:#x}
    scratch:
        add x0, x21, #0xa0
        bl pick
        ldr w1, [x21, #0xa4]
        adrp x0, {SCRATCH_X0_PAGE:#x}
        b {SCRATCH_RESUME:#x}
    pick:
        stp x29, x30, [sp, #-32]!
        str x19, [sp, #16]
        mov x19, x0
        ldr w0, [x19]
        cmp w0, #9
        b.ne done
        ldr w1, [x19, #4]
        cmn w1, #1
        b.ne done
        ldr w0, [x19, #0x1c]
        mov w1, #3
        cmp w0, #4
        b.ne not_golden
        mov w1, #4
    not_golden:
        cmp w0, #17
        b.ne not_seasonal
        mov w1, #8
    not_seasonal:
        cmp w0, #27
        b.ne not_challenge
        mov w1, #12
    not_challenge:
        adrp x2, {UNIVERSE_GOT & ~0xfff:#x}
        ldr x2, [x2, #{UNIVERSE_GOT & 0xfff:#x}]
        ldr x2, [x2]
        ldr x2, [x2, #8]
        ldr w2, [x2, #0x934]
        ldr w3, [x19, #0x10]
        mov w4, #0
        adrp x0, {CREATURE_MANAGER_GOT & ~0xfff:#x}
        ldr x0, [x0, #{CREATURE_MANAGER_GOT & 0xfff:#x}]
        ldr x0, [x0]
        bl {HATCH_SIMULATION:#x}
        str w0, [x19, #4]
    done:
        ldr x19, [sp, #16]
        ldp x29, x30, [sp], #32
        ret
    """, CAVE)[0])
    assert CAVE + len(cave) <= CAVE_END
    md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)
    for i in md.disasm(cave, CAVE):
        if i.mnemonic.startswith(("b.", "cbz", "cbnz")):
            assert CAVE <= int(i.op_str.split("#")[-1], 16) < CAVE_END, f"far conditional branch: {i}"
    return {
        CAVE: cave,
        CLAIM_HOOK: bytes(ks.asm(f"b {CAVE:#x}", CLAIM_HOOK)[0]),
        SCRATCH_HOOK: bytes(ks.asm(f"b {CAVE + 0x10:#x}", SCRATCH_HOOK)[0]),
    }


if __name__ == "__main__":
    import capstone, os
    lib = os.path.join(os.path.dirname(__file__), "..", "binaries", "libuaf_original.so")
    md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)
    for a, b in assemble(open(lib, "rb").read()).items():
        print(f"; {a:#x}")
        for i in md.disasm(b, a):
            print(f"  {i.address:#x}: {i.mnemonic} {i.op_str}")
