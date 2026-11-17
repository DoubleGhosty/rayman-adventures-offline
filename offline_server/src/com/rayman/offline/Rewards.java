package com.rayman.offline;

import android.util.Log;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.List;
import java.util.Random;

/**
 * Lucky ticket draws with Ubisoft's own weight tables.
 *
 * The tables ship in the game data (RLC_InAppPurchaseManager_Template: ticketCategoryWeights*,
 * ticketNormalRewardWeights*, ticketJackpotRewardWeights*, ticketEggRarityWeights* for the Simple,
 * Golden and Chocolate tickets) but the client never uses them: the draw was server-side. They are
 * dumped from the running game by tools/re/dump_ticket_weights.py into mock_data/ticket_weights.json
 * (asset offline/ticket_weights.json). A draw = category (Normal / Jackpot / Egg) by weight, then a
 * reward of that category's table by weight.
 *
 * Reading of the tables:
 * - the first row of each Normal table has type 0 ("_unknown") with a gems-like count (Simple
 *   25 / 30 / 35, Chocolate 10 / 20 / 30, the Golden table has Gems 30 / 50 / 70): taken as Gems;
 * - rows with weight 0 are never drawn; in the egg rarity tables only the first row of a rarity is
 *   used (stray duplicates with key 16).
 * - Egg rewards carry creatureID = invalid and the rarity in elixirType0; the game picks a creature
 *   of that rarity itself (scripts/ticket_hooks.py).
 *
 * RLC_LuckyTicketReward.type: Gems=1 Costume=2 LuckyTicket=3 GoldenTicket=4 Food=8 Egg=9 Elixirs=10
 * AllElixirPack=11 TwoElixirs=12 (display only: credits nothing) SeasonalCurrency=16
 * SeasonalTicket=17 MagnifyingGlass=19 ChallengeTicket=27.
 * Elixirs credits `count` of each non-zero elixirType0..2 (RLC_ElixirType: 1 speed, 2 silver egg,
 * 3 gold egg, 4 new creature).
 */
final class Rewards {

    private static final String TAG = OfflineServer.TAG;

    static final int GEMS = 1;
    static final int LUCKY_TICKET = 3;
    static final int GOLDEN_TICKET = 4;
    static final int FOOD = 8;
    static final int EGG = 9;
    static final int ELIXIRS = 10;
    static final int SEASONAL_TICKET = 17;
    static final long NO_CREATURE = 4294967295L;
    static final String[] RARITIES = {"common", "unCommon", "rare", "epic", "legendary", "queen"};

    private static final Random RNG = new Random();
    private static JSONObject tables = new JSONObject();

    /** Forced next draw (admin tool, testing): null = normal draw. */
    static JSONObject forced;

    private Rewards() {
    }

    static void load(String json) {
        try {
            tables = new JSONObject(json);
            Log.i(TAG, "ticket weight tables loaded (" + tables.length() + ")");
        } catch (JSONException e) {
            Log.e(TAG, "bad ticket_weights.json", e);
        }
    }

    /** Table family of a ticket: Simple, Golden or Chocolate. */
    static String ticketKind(int ticketType) {
        if (ticketType == GOLDEN_TICKET) {
            return "Golden";
        }
        if (ticketType == SEASONAL_TICKET) {
            return "Chocolate";
        }
        return "Simple";
    }

    static JSONObject draw(int ticketType, boolean decoy) throws JSONException {
        if (forced != null && !decoy) {
            JSONObject r = forced;
            forced = null;
            r.put("ticketType", ticketType);
            return r;
        }
        String kind = ticketKind(ticketType);
        String category = pick(tables.optJSONArray("ticketCategoryWeights" + kind), "category");
        if (category == null) {
            category = "Normal";
        }
        if (decoy && !category.equals("Normal")) {
            category = "Normal";     // getDecoyReward: a plain reward, never a jackpot or an egg
        }
        if (category.equals("Egg")) {
            String rarity = pick(firstPerRarity(tables.optJSONArray("ticketEggRarityWeights" + kind)), "rarity");
            int r = rarityIndex(rarity == null ? "common" : rarity);
            return reward(EGG, 1, r, 0, 0, ticketType, false);
        }
        JSONObject row = pickRow(tables.optJSONArray("ticket" + category + "RewardWeights" + kind));
        if (row == null) {
            row = pickRow(tables.optJSONArray("ticketNormalRewardWeightsSimple"));
        }
        if (row == null) {
            return reward(FOOD, 5, 0, 0, 0, ticketType, false);
        }
        int type = row.optInt("typeId", GEMS);
        if (type == 0) {
            type = GEMS;
        }
        JSONArray el = row.optJSONArray("elixirs");
        int e0 = el != null && el.length() > 0 ? el.getInt(0) : 0;
        int e1 = el != null && el.length() > 1 ? el.getInt(1) : 0;
        int e2 = el != null && el.length() > 2 ? el.getInt(2) : 0;
        return reward(type, row.optInt("count", 1), e0, e1, e2, ticketType, category.equals("Jackpot"));
    }

    private static JSONArray firstPerRarity(JSONArray rows) throws JSONException {
        JSONArray out = new JSONArray();
        List<String> seen = new ArrayList<String>();
        if (rows == null) {
            return out;
        }
        for (int i = 0; i < rows.length(); i++) {
            String r = rows.getJSONObject(i).optString("rarity");
            if (!seen.contains(r)) {
                seen.add(r);
                out.put(rows.getJSONObject(i));
            }
        }
        return out;
    }

    static int rarityIndex(String name) {
        for (int i = 0; i < RARITIES.length; i++) {
            if (RARITIES[i].equals(name)) {
                return i;
            }
        }
        return 0;
    }

    /** Weighted pick of rows[i].field (rows with weight 0 are never picked). */
    private static String pick(JSONArray rows, String field) throws JSONException {
        JSONObject row = pickRow(rows);
        return row == null ? null : row.optString(field, null);
    }

    private static JSONObject pickRow(JSONArray rows) throws JSONException {
        if (rows == null) {
            return null;
        }
        int total = 0;
        for (int i = 0; i < rows.length(); i++) {
            total += Math.max(0, rows.getJSONObject(i).optInt("weight", 0));
        }
        if (total <= 0) {
            return null;
        }
        int roll = RNG.nextInt(total);
        for (int i = 0; i < rows.length(); i++) {
            JSONObject row = rows.getJSONObject(i);
            int w = Math.max(0, row.optInt("weight", 0));
            if (roll < w) {
                return row;
            }
            roll -= w;
        }
        return null;
    }

    static JSONObject reward(int type, int count, int e0, int e1, int e2, int ticketType, boolean jackpot)
            throws JSONException {
        JSONObject r = new JSONObject();
        r.put("type", type);
        r.put("creatureID", NO_CREATURE);
        r.put("count", count);
        r.put("elixirType0", e0);
        r.put("elixirType1", e1);
        r.put("elixirType2", e2);
        r.put("ticketType", ticketType);
        r.put("jackpot", jackpot);
        r.put("seasonalFixedReward", false);
        return r;
    }

    /** Admin tool: n draws of a ticket type, counted by (type, count, elixirs, jackpot). */
    static JSONObject histogram(int ticketType, int n) throws JSONException {
        java.util.TreeMap<String, Integer> counts = new java.util.TreeMap<String, Integer>();
        for (int i = 0; i < n; i++) {
            JSONObject r = draw(ticketType, false);
            String key = "type=" + r.getInt("type") + " count=" + r.getInt("count")
                    + " elixirs=" + r.getInt("elixirType0") + "," + r.getInt("elixirType1")
                    + (r.getBoolean("jackpot") ? " jackpot" : "");
            Integer c = counts.get(key);
            counts.put(key, c == null ? 1 : c + 1);
        }
        JSONObject out = new JSONObject();
        for (java.util.Map.Entry<String, Integer> e : counts.entrySet()) {
            out.put(e.getKey(), String.format(java.util.Locale.US, "%d (%.2f%%)", e.getValue(),
                    100.0 * e.getValue() / n));
        }
        return out;
    }
}
