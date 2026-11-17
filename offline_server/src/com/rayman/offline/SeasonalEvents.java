package com.rayman.offline;

import android.util.Log;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.util.Calendar;

/**
 * Seasonal events (hunt, spin wheel, marathon): their calendar, served as game globals.
 *
 * The game knows its events but ships with none scheduled: RLC_SeasonalEventManager reads the current
 * one from the template enginedata/gameconfig/seasonaleventconfig.isg, whose cooked file has no event
 * (currentSeasonalEventID2 = 0, null dates). Ubisoft scheduled them by overriding that template from
 * the game server: GET v1/gameglobals/getGameGlobals -> gameGlobalsContainer {data: gameGlobalsData}
 *   gameGlobalsData {variables, overrides: map<StringID(path), GameGlobalsFile {overrides: [
 *       GameGlobalsOverride {json, condition: GameGlobalsComplexCondition {conditions, needAll,
 *       priority, hotReload}, name}]}>, versionTime}
 * The json is applied onto the loaded template (gameGlobals::getOverride: JSON group "params", then
 * the template's own Serialize), an empty condition list is always valid. The game downloads the
 * globals when userprofile/meta's gameGlobals.versionTime differs from its cached copy, so versionTime
 * changes with each scheduled event.
 *
 * Event ids (RLC_SeasonalEventManager::eSeasonalEvent, type from getEventType, costume from
 * getCurrentSeasonalEventCostume): hunts 1 Easter (Teensy Bunny), 2 Summer (Globox Summer),
 * 3 Halloween (Globox Halloween), 5 Winter (Barbara Winter), 6 Renaissance (Rayman Renaissance),
 * 9 Raybeard's treasure (Rayman Raybeard); spin wheels 7 Fiesta (Globox Glombrero), 10 Hell-O-Wheel
 * (Barbara Hellen), 13 Space (Rayman Spaceray), 17 Ice Age (Barbara IceAge); marathons 8 Land of the
 * Livid Dead (Rayman Raybolt), 11 Desert Kingdom (Globox Egyptian), 12 Sakura (Barbara Sakura),
 * 16 RayWiz (Rayman RayWiz). Id 4 (a hunt without costume) is left out.
 *
 * Calendar (our choice, Ubisoft's is lost): the year is cut into 14 slots of 26 days from January 1st
 * (device time), one event per slot, roughly in season: 23 days of event, then 3 "last chance" days to
 * spend the event currency (currentSeasonalEventCompleteEndingTime2), then the next one starts.
 */
final class SeasonalEvents {

    private static final String TAG = OfflineServer.TAG;

    /** StringID of "enginedata/gameconfig/seasonaleventconfig.isg" (tools/re/stringid.py). */
    static final long CONFIG_PATH_ID = 584237580L;

    static final int SLOT_DAYS = 26;
    static final int EVENT_DAYS = 23;
    /** Event of each slot, from January 1st. */
    static final int[] CALENDAR = {17, 12, 6, 1, 7, 11, 9, 2, 16, 13, 8, 3, 10, 5};
    static final String[] NAMES = {"", "Easter Egg Hunt", "Summer Hunt", "Halloween Hunt", "", "Winter Hunt",
            "Renaissance Hunt", "Spin Wheel Fiesta", "Land of the Livid Dead Marathon", "Raybeard's Treasure Hunt",
            "Hell-O-Wheel", "Desert Kingdom Marathon", "Sakura Marathon", "Space Wheel", "", "", "RayWiz Marathon",
            "Ice Age Wheel"};

    private SeasonalEvents() {
    }

    /** Current event: {id, start, end, completeEnd} (millis), id 0 = none. */
    static long[] current() {
        long now = System.currentTimeMillis();
        JSONObject s = ServerState.section("seasonalEvents");
        if (s.has("forcedId") && s.optLong("forcedCompleteEnd", 0) > now) {
            return new long[] {s.optInt("forcedId"), s.optLong("forcedStart"), s.optLong("forcedEnd"),
                    s.optLong("forcedCompleteEnd")};
        }
        Calendar c = Calendar.getInstance();
        c.setTimeInMillis(now);
        int slot = Math.min((c.get(Calendar.DAY_OF_YEAR) - 1) / SLOT_DAYS, CALENDAR.length - 1);
        c.set(Calendar.DAY_OF_YEAR, 1 + slot * SLOT_DAYS);
        c.set(Calendar.HOUR_OF_DAY, 0);
        c.set(Calendar.MINUTE, 0);
        c.set(Calendar.SECOND, 0);
        c.set(Calendar.MILLISECOND, 0);
        long start = c.getTimeInMillis();
        c.add(Calendar.DAY_OF_YEAR, EVENT_DAYS);
        long end = c.getTimeInMillis();
        if (slot == CALENDAR.length - 1) {
            c.set(Calendar.DAY_OF_YEAR, c.getActualMaximum(Calendar.DAY_OF_YEAR));   // last slot: to December 31st
            c.add(Calendar.DAY_OF_YEAR, 1);
        } else {
            c.add(Calendar.DAY_OF_YEAR, SLOT_DAYS - EVENT_DAYS);
        }
        return new long[] {CALENDAR[slot], start, end, c.getTimeInMillis()};
    }

    /** gameGlobals.versionTime of userprofile/meta: changes with each scheduled event. */
    static String versionTime() {
        return Incubator.format(current()[1]);
    }

    /** GET v1/gameglobals/getGameGlobals. */
    static JSONObject gameGlobals() throws JSONException {
        long[] ev = current();
        JSONObject params = new JSONObject();
        params.put("currentSeasonalEventID2", (int) ev[0]);
        params.put("currentSeasonalEventStartingTime2", Incubator.format(ev[1]));
        params.put("currentSeasonalEventEndingTime2", Incubator.format(ev[2]));
        params.put("currentSeasonalEventCompleteEndingTime2", Incubator.format(ev[3]));
        // same shape as Ubisoft's overrides (gameglobals.isg.ckd): the template's fields + _CLASS_NAME
        params.put("_CLASS_NAME", "RLC_SeasonalEventManager_Template");
        JSONObject json = params;

        JSONObject condition = new JSONObject();
        condition.put("conditions", new JSONArray());
        condition.put("needAll", true);
        condition.put("priority", 0);
        condition.put("hotReload", true);
        JSONObject override = new JSONObject();
        override.put("json", json.toString());
        override.put("condition", condition);
        override.put("name", "offlineSeasonalEvent");
        JSONObject file = new JSONObject();
        file.put("overrides", new JSONArray().put(override));
        // ITF JSON maps are objects: the member name is the KEY (a StringID as digits), the member the
        // VAL (an array of {"KEY","VAL"} reads KEY = 0 and the value one level too deep)
        JSONObject files = new JSONObject();
        files.put(Long.toString(CONFIG_PATH_ID), file);

        JSONObject data = new JSONObject();
        data.put("variables", "");
        data.put("overrides", files);
        data.put("versionTime", versionTime());
        JSONObject out = new JSONObject();
        out.put("data", encrypt(data.toString()));
        Log.i(TAG, "seasonal event: " + (ev[0] == 0 ? "none" : NAMES[(int) ev[0]] + " (id " + ev[0] + ") "
                + Incubator.format(ev[1]) + " -> " + Incubator.format(ev[2]) + " / " + Incubator.format(ev[3])));
        return out;
    }

    /**
     * gameGlobalsContainer::SerializeImpl reads "data" inside StartEncryption("data", TeaKey(...)): in
     * JSON, a string = base64 of the XXTEA-encrypted text of the object (SerializerJson::StartEncryption
     * -> ITF::Tea::decode: base64, little-endian words, btea with -n, zero bytes dropped). Checked by
     * decrypting the game's own enginedata/online/gameglobals.isg.ckd with the same key.
     */
    private static final int[] TEA_KEY = {0x2d8441f7, 0xe30865fc, 0xc9f5b992, 0x03bb7669};
    private static final int DELTA = 0x9e3779b9;

    static String encrypt(String text) {
        byte[] b = text.getBytes(java.nio.charset.Charset.forName("UTF-8"));
        int n = Math.max(2, (b.length + 3) / 4);
        int[] v = new int[n];
        for (int i = 0; i < b.length; i++) {
            v[i / 4] |= (b[i] & 0xff) << (8 * (i % 4));
        }
        int z = v[n - 1];
        int y;
        int sum = 0;
        for (int q = 6 + 52 / n; q > 0; q--) {
            sum += DELTA;
            int e = (sum >>> 2) & 3;
            int p;
            for (p = 0; p < n - 1; p++) {
                y = v[p + 1];
                v[p] += mx(sum, y, z, p, e);
                z = v[p];
            }
            y = v[0];
            v[n - 1] += mx(sum, y, z, p, e);
            z = v[n - 1];
        }
        byte[] out = new byte[n * 4];
        for (int i = 0; i < out.length; i++) {
            out[i] = (byte) (v[i / 4] >>> (8 * (i % 4)));
        }
        return android.util.Base64.encodeToString(out, android.util.Base64.NO_WRAP);
    }

    private static int mx(int sum, int y, int z, int p, int e) {
        return (((z >>> 5) ^ (y << 2)) + ((y >>> 3) ^ (z << 4))) ^ ((sum ^ y) + (TEA_KEY[(p & 3) ^ e] ^ z));
    }

    /** Admin: runs event id now for the given days (id 0 = back to the calendar). */
    static JSONObject force(int id, double days) throws JSONException {
        JSONObject s = ServerState.section("seasonalEvents");
        if (id <= 0) {
            s.remove("forcedId");
        } else {
            long now = System.currentTimeMillis();
            long end = now + (long) (days * 86400000L);
            s.put("forcedId", id);
            s.put("forcedStart", now - 60000L);
            s.put("forcedEnd", end);
            s.put("forcedCompleteEnd", end + 3 * 86400000L);
        }
        ServerState.save();
        return gameGlobals();
    }
}
