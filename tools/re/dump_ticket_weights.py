"""Dumps the lucky-ticket weight tables of RLC_InAppPurchaseManager_Template from the running game.

These are Ubisoft's own tables, shipped in the game data (the client only loads them; the draw
itself was done by the server). Needs a rooted device with the game running.

    python tools/re/dump_ticket_weights.py [out.json]
"""
import json, os, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from memread import Mem

IAP_GOT = 0x24aa8a8          # -> RLC_InAppPurchaseManager*
TEMPLATE = 0x80              # RLC_InAppPurchaseManager::m_template
CATEGORY = ["Normal", "Jackpot", "Egg"]
RARITY = ["common", "unCommon", "rare", "epic", "legendary", "queen", "unknown"]
REWARD_TYPES = {0: "_unknown", 1: "Gems", 2: "Costume", 3: "LuckyTicket", 4: "GoldenTicket", 5: "Region",
                6: "Family", 7: "HunterLevel", 8: "Food", 9: "Egg", 10: "Elixirs", 11: "AllElixirPack",
                12: "TwoElixirs", 13: "ThreeElixirs", 19: "MagnifyingGlass"}
TABLES = {
    "ticketCategoryWeightsSimple": (0x770, "category"),
    "ticketCategoryWeightsGolden": (0x7c0, "category"),
    "ticketCategoryWeightsChocolate": (0x8b0, "category"),
    "ticketNormalRewardWeightsSimple": (0x900, "reward"),
    "ticketNormalRewardWeightsGolden": (0x950, "reward"),
    "ticketNormalRewardWeightsChocolate": (0xa40, "reward"),
    "ticketJackpotRewardWeightsSimple": (0xa90, "reward"),
    "ticketJackpotRewardWeightsGolden": (0xae0, "reward"),
    "ticketJackpotRewardWeightsChocolate": (0xbd0, "reward"),
    "ticketEggRarityWeightsSimple": (0xc20, "rarity"),
    "ticketEggRarityWeightsGolden": (0xc70, "rarity"),
    "ticketEggRarityWeightsChocolate": (0xd60, "rarity"),
    "DailyRewards": (0xdb0, "dailyreward"),
}
# SacRBTree: header {left/min, right/max, parent/root, ?, u32 size @+0x20}
# node {left @0, right @8, parent @0x10, u32 color @0x18, u32 key @0x1c, value @0x20}


def nodes(m, header):
    count = m.d(header + 0x20)
    root = m.q(header + 0x10)
    out = []

    def walk(n, depth=0):
        if not n or depth > 64 or n == header:
            return
        walk(m.q(n), depth + 1)
        out.append(n)
        walk(m.q(n + 8), depth + 1)
    walk(root)
    assert len(out) == count, f"walked {len(out)} nodes, map size {count}"
    return out


def reward(b):
    t, cid, _, count, e0, e1, e2, ticket = struct.unpack_from("<8I", b, 0)
    return {"type": REWARD_TYPES.get(t, t), "typeId": t, "creatureID": cid, "count": count,
            "elixirs": [e for e in (e0, e1, e2) if e], "ticketType": ticket,
            "jackpot": bool(b[0x20]), "seasonalFixedReward": bool(b[0x21])}


def main():
    m = Mem()
    tpl = m.q(m.q(m.q(m.base + IAP_GOT)) + TEMPLATE)
    result = {}
    for name, (off, kind) in TABLES.items():
        rows = []
        for n in nodes(m, tpl + off):
            key = m.d(n + 0x1c)
            v = m.read(n + 0x20, 0x28)
            if kind == "category":
                c, w = struct.unpack_from("<II", v)
                rows.append({"key": key, "category": CATEGORY[c] if c < 3 else c, "weight": w})
            elif kind == "rarity":
                r, w = struct.unpack_from("<II", v)
                rows.append({"key": key, "rarity": RARITY[r] if r < 7 else r, "weight": w})
            elif kind == "reward":
                row = {"key": key, "weight": struct.unpack_from("<I", v, 0x24)[0]}
                row.update(reward(v))
                rows.append(row)
            else:
                row = {"key": key}
                row.update(reward(v))
                rows.append(row)
        result[name] = rows
    text = json.dumps(result, indent=1)
    if len(sys.argv) > 1:
        open(sys.argv[1], "w").write(text)
    print(text)


if __name__ == "__main__":
    main()
