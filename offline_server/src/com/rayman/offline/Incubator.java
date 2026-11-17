package com.rayman.offline;

import android.util.Log;

import org.json.JSONException;
import org.json.JSONObject;

import java.text.ParseException;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;
import java.util.TimeZone;

/**
 * Server-side incubator ("v2/incubator/*"), state kept in profile.incubationData
 * (online::incubationStatusResult). Answer formats (libuaf RLC_Incubator::onGameServerRequestDone):
 *   startIncubationResult {hatchingDuration, hatchingEnd, eggAdventureSequence, eggAdventureRegion, decoyRewardType}
 *   useElixirResult       {hatchingEnd, timeLeft, usedElixir, eggAdventureSequence, eggAdventureRegion}
 *   HatchCreatureResult   {creatureId, rarity, acquisition, decoyRewardType, decoyReward}
 *   HatchSimulationResult {creatureId, rarity, elixirUsed, decoyRewardType, decoyReward}
 * The original hatching durations were server-side; HATCH_SECONDS is our choice.
 */
final class Incubator {

    private static final String TAG = OfflineServer.TAG;

    /** Hatching time of an egg put in the incubator. */
    static final long HATCH_SECONDS = 30 * 60;

    static final int ELIXIR_SPEED = 1;
    static final int ELIXIR_HATCH_NOW = 5;
    static final long NO_CREATURE = 4294967295L;

    private Incubator() {
    }

    static JSONObject status() throws JSONException {
        return status(new JSONObject());
    }

    /**
     * incubationStatus(autoHatch). When the client asks with autoHatch=true (egg tapped) and the
     * hatching time is over, the answer carries autoHatch=true + the egg's creatureId: the client
     * then builds the RLC_EggData and calls RLC_Incubator::pickEggFromIncubator (hatching ritual).
     * The server-side incubator is emptied at that point.
     */
    static JSONObject status(JSONObject in) throws JSONException {
        JSONObject inc = ProfileStore.incubation();
        double left = timeLeft(inc);
        inc.put("timeLeft", left);
        long end = parse(inc.optString("hatchingEnd", ""));
        if (end > 0) {
            inc.put("hatchingEnd", format(end));   // dates stored by older builds were UTC
        }
        long creature = inc.optLong("creatureId", NO_CREATURE);
        if (in.optBoolean("autoHatch", false) && left <= 0 && creature != NO_CREATURE) {
            JSONObject out = new JSONObject(inc.toString());
            out.put("autoHatch", true);
            ProfileStore.get().put("incubationData", ProfileStore.emptyIncubation());
            ProfileStore.save();
            Log.i(TAG, "incubator: egg " + creature + " hatched (autoHatch)");
            return out;
        }
        inc.put("autoHatch", false);
        if (creature == NO_CREATURE) {
            // "unknown egg" rather than "empty incubator": an empty answer makes the client delete
            // its local egg (RLC_Incubator::flushIncubator), which would destroy eggs incubated by
            // builds that did not register them here. With 410 the client keeps its egg, and on an
            // autoHatch request hatches it locally (scripts/incubator_hooks.py).
            OfflineServer.setStatus(HTTP_UNKNOWN_EGG);
        }
        return inc;
    }

    /** HTTP status of incubationStatus when the server has no egg (see status()). */
    static final int HTTP_UNKNOWN_EGG = 410;

    static JSONObject startIncubation(JSONObject in) throws JSONException {
        JSONObject inc = ProfileStore.incubation();
        long now = System.currentTimeMillis();
        long end = now + HATCH_SECONDS * 1000;
        inc.put("creatureId", in.optLong("creatureId", NO_CREATURE));
        inc.put("eggAdventureSequence", in.optLong("eggAdventureSequence", 0));
        inc.put("eggAdventureRegion", in.optLong("eggAdventureRegion", 0));
        inc.put("hatchingEnd", format(end));
        inc.put("timeLeft", (double) HATCH_SECONDS);
        inc.put("autoHatch", false);
        inc.put("elixirUsed", 0);
        ProfileStore.save();
        JSONObject out = new JSONObject();
        out.put("hatchingDuration", HATCH_SECONDS);
        out.put("hatchingEnd", inc.getString("hatchingEnd"));
        out.put("eggAdventureSequence", inc.getLong("eggAdventureSequence"));
        out.put("eggAdventureRegion", inc.getLong("eggAdventureRegion"));
        out.put("decoyRewardType", 0);
        return out;
    }

    static JSONObject useElixir(JSONObject in) throws JSONException {
        JSONObject inc = ProfileStore.incubation();
        int type = in.optInt("elixirType", ELIXIR_SPEED);
        int count = Math.max(1, in.optInt("numElixirSpeed", 1));
        double left = timeLeft(inc);
        if (type == ELIXIR_SPEED) {
            for (int i = 0; i < count; i++) {
                left /= 2;      // "Elixir_skip_time_50_percent"
            }
            if (left < 1) {
                left = 0;
            }
        } else if (type == ELIXIR_HATCH_NOW) {
            left = 0;
        } else {
            inc.put("elixirUsed", type);   // upgrade / force-new elixirs act at hatching time
        }
        inc.put("hatchingEnd", format(System.currentTimeMillis() + (long) (left * 1000)));
        inc.put("timeLeft", left);
        ProfileStore.save();
        JSONObject out = new JSONObject();
        out.put("hatchingEnd", inc.getString("hatchingEnd"));
        out.put("timeLeft", left);
        out.put("usedElixir", type);
        out.put("eggAdventureSequence", inc.optLong("eggAdventureSequence", 0));
        out.put("eggAdventureRegion", inc.optLong("eggAdventureRegion", 0));
        return out;
    }

    /** hatchingRitual / hatchCreature: hatches the incubated creature and empties the incubator. */
    static JSONObject hatch(JSONObject in) throws JSONException {
        JSONObject inc = ProfileStore.incubation();
        long creature = in.optLong("overrideIncubationCreatureId", NO_CREATURE);
        if (creature == NO_CREATURE || creature == 0) {
            creature = in.optLong("creatureId", NO_CREATURE);
        }
        if (creature == NO_CREATURE || creature == 0) {
            creature = inc.optLong("creatureId", NO_CREATURE);
        }
        JSONObject out = result(creature, in.optInt("forcedRarity", 0));
        out.put("acquisition", in.optInt("acquisition", 0));
        JSONObject empty = ProfileStore.emptyIncubation();
        ProfileStore.get().put("incubationData", empty);
        ProfileStore.save();
        Log.i(TAG, "incubator: hatched creature " + creature);
        return out;
    }

    static JSONObject simulate(JSONObject in) throws JSONException {
        long creature = in.optLong("overrideIncubationCreatureId", NO_CREATURE);
        if (creature == NO_CREATURE || creature == 0) {
            creature = ProfileStore.incubation().optLong("creatureId", NO_CREATURE);
        }
        JSONObject out = result(creature, in.optInt("forcedRarity", 0));
        out.put("elixirUsed", in.optInt("elixirUsed", 0));
        return out;
    }

    /** Creature_Rarity::unknown: "let the game pick" (scripts/egg_pick_hooks.py). */
    static final int RARITY_UNKNOWN = 6;

    /** One Charlie (hidden extra egg) every CHARLIE_EVERY adventures on average - our choice. */
    static final int CHARLIE_EVERY = 4;

    /**
     * magnifyingGlassNextAdventure(regions, previousResult, exclude, forcedRarity, forceNewCreature)
     * -> MagnifyingGlassNextAdventureResult {results[HatchSimulationResult]}, one per region: the eggs
     * of the next adventures. The creature is left to the game (invalid id, rarity = forcedRarity or
     * unknown), which picks it with its own rules.
     */
    static JSONObject magnifyingGlass(JSONObject in) throws JSONException {
        org.json.JSONArray regions = in.optJSONArray("regions");
        int n = regions == null ? 1 : Math.max(1, regions.length());
        int rarity = in.optInt("forcedRarity", RARITY_UNKNOWN);
        if (rarity < 0 || rarity > RARITY_UNKNOWN) {
            rarity = RARITY_UNKNOWN;
        }
        org.json.JSONArray results = new org.json.JSONArray();
        for (int i = 0; i < n; i++) {
            JSONObject r = result(NO_CREATURE, rarity);
            r.put("elixirUsed", 0);
            results.put(r);
        }
        JSONObject out = new JSONObject();
        out.put("results", results);
        return out;
    }

    /**
     * getCharlie(region, forceCharlie, forceDecoy, forceNew) -> charlieResult {charlie (1 = a hidden
     * extra egg in this adventure), charlieCreatureId, decoyRewardType, decoyReward}. The original
     * frequency was server-side; the creature is picked by the game (scripts/egg_pick_hooks.py).
     */
    static JSONObject charlie(JSONObject in) throws JSONException {
        boolean present = forceNextCharlie || in.optBoolean("forceCharlie", false) || RNG.nextInt(CHARLIE_EVERY) == 0;
        forceNextCharlie = false;
        JSONObject out = new JSONObject();
        out.put("charlie", present ? 1 : 0);
        out.put("charlieCreatureId", NO_CREATURE);
        out.put("decoyRewardType", 0);
        out.put("decoyReward", ProfileStore.emptyIncubation().getJSONObject("decoyReward"));
        Log.i(TAG, "getCharlie: " + (present ? "hidden egg in this adventure" : "none"));
        return out;
    }

    private static final java.util.Random RNG = new java.util.Random();

    /** Admin tool: the next getCharlie answers "present". */
    static boolean forceNextCharlie;

    private static JSONObject result(long creature, int rarity) throws JSONException {
        JSONObject out = new JSONObject();
        out.put("creatureId", creature);
        out.put("rarity", rarity);
        out.put("decoyRewardType", 0);
        out.put("decoyReward", ProfileStore.emptyIncubation().getJSONObject("decoyReward"));
        return out;
    }

    private static double timeLeft(JSONObject inc) {
        long end = parse(inc.optString("hatchingEnd", ""));
        if (end <= 0) {
            return 0;
        }
        return Math.max(0, (end - System.currentTimeMillis()) / 1000.0);
    }

    /**
     * ITF DateTime text in the device's local time with its offset ("2026-11-16T13:03:35+01:00").
     * The game reads the clock part as local time (a UTC "+00:00" date showed the mini event timer
     * one hour short in France), so dates must be local; the offset keeps them exact for any reader.
     */
    static String format(long millis) {
        TimeZone tz = TimeZone.getDefault();
        SimpleDateFormat f = new SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss", Locale.US);
        f.setTimeZone(tz);
        int off = tz.getOffset(millis) / 60000;
        char sign = off < 0 ? '-' : '+';
        off = Math.abs(off);
        return f.format(new Date(millis)) + String.format(Locale.US, "%c%02d:%02d", sign, off / 60, off % 60);
    }

    /** Parses the ITF DateTime format "2026-11-16T01:14:42+01:00" (0 for the null date). */
    static long parse(String s) {
        if (s == null || s.length() < 19 || s.startsWith("0000")) {
            return 0;
        }
        try {
            SimpleDateFormat f = new SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss", Locale.US);
            f.setTimeZone(TimeZone.getTimeZone("UTC"));
            long t = f.parse(s.substring(0, 19)).getTime();
            if (s.length() >= 25) {
                int sign = s.charAt(19) == '-' ? -1 : 1;
                int h = Integer.parseInt(s.substring(20, 22));
                int m = Integer.parseInt(s.substring(23, 25));
                t -= sign * (h * 3600L + m * 60L) * 1000L;
            }
            return t;
        } catch (ParseException | NumberFormatException e) {
            return 0;
        }
    }
}
