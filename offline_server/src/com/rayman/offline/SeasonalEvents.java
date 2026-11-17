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
 * Event ids (RLC_SeasonalEventManager::eSeasonalEvent, type from getEventType): hunts 1, 2, 3, 5, 6, 9;
 * spin wheels 7, 10, 13, 17; marathons 8, 11, 12, 16. Seen in game (2026-11-17): 3 = "La chasse au
 * tresor de Raybarbe" (doubloons hidden in the game; shop: Jolly-Roger ticket, sunken egg, Raybarbe),
 * 8 = a marathon (the daily challenge in event mode, shop "Echoppe": parchment ticket, Chatoeuf,
 * Raystidigitateur), 10 = "Expedition Rayhistorik" (Captain's wheel, prehistoric meat, shop
 * "Maglace-Zin": fur ticket, frozen egg, Barbarrrrr).
 * Id 4 (a hunt without costume) is left out. The game shows events from the 6th adventure on
 * (canDisplaySeasonalEvent: universe+0x724 > 4), with an intro popup once a day on the map.
 *
 * Calendar (our choice, Ubisoft's is lost): the year is cut into 14 slots of 26 days from January 1st
 * (device time), one event per slot: 23 days of event, then 3 "last chance" days to spend the event
 * currency (currentSeasonalEventCompleteEndingTime2), then the next one starts. The whole calendar of
 * YEARS years goes in one download, one override per event with a GameGlobalsDateIntervalCondition
 * (polymorphic JSON object, "_CLASS_NAME"): the game picks the current event itself at each launch.
 * The title-screen login that sends userprofile/meta (and so the download) does not always succeed
 * after a restart; with the whole calendar cached this no longer matters.
 */
final class SeasonalEvents {

    private static final String TAG = OfflineServer.TAG;

    /** StringID of "enginedata/gameconfig/seasonaleventconfig.isg" (tools/re/stringid.py). */
    static final long CONFIG_PATH_ID = 584237580L;

    static final int SLOT_DAYS = 26;
    static final int EVENT_DAYS = 23;
    /** Event of each slot, from January 1st. */
    static final int[] CALENDAR = {17, 12, 6, 1, 7, 11, 9, 2, 16, 13, 8, 3, 10, 5};
    /** Log labels (type; names seen in game for 3, 8 and 10, the others from their costume constant). */
    static final String[] NAMES = {"", "hunt 1", "hunt 2", "hunt La chasse au tresor de Raybarbe", "",
            "hunt 5", "hunt 6", "wheel 7", "marathon 8 (shop Echoppe: Chatoeuf, Raystidigitateur)", "hunt 9",
            "wheel Expedition Rayhistorik", "marathon 11", "marathon 12", "wheel 13", "", "", "marathon 16",
            "wheel 17"};

    private SeasonalEvents() {
    }

    /** Years of calendar sent at once (from the current one): the game picks the event itself. */
    static final int YEARS = 5;

    /** Forced event {id, start, end, completeEnd} (admin), or null. */
    static long[] forced() {
        JSONObject s = forcedState();
        if (s.has("forcedId") && s.optLong("forcedCompleteEnd", 0) > System.currentTimeMillis()) {
            return new long[] {s.optInt("forcedId"), s.optLong("forcedStart"), s.optLong("forcedEnd"),
                    s.optLong("forcedCompleteEnd")};
        }
        return null;
    }

    /** Event of a calendar slot: {id, start, end, completeEnd} (millis, device time zone). */
    static long[] slot(int year, int slot) {
        Calendar c = Calendar.getInstance();
        c.clear();
        c.set(Calendar.YEAR, year);
        c.set(Calendar.DAY_OF_YEAR, 1 + slot * SLOT_DAYS);
        long start = c.getTimeInMillis();
        c.add(Calendar.DAY_OF_YEAR, EVENT_DAYS);
        long end = c.getTimeInMillis();
        if (slot == CALENDAR.length - 1) {
            c.clear();
            c.set(Calendar.YEAR, year + 1);                // last slot: to December 31st
        } else {
            c.add(Calendar.DAY_OF_YEAR, SLOT_DAYS - EVENT_DAYS);
        }
        return new long[] {CALENDAR[slot], start, end, c.getTimeInMillis()};
    }

    /** Current event (logs, versionTime). */
    static long[] current() {
        long[] f = forced();
        if (f != null) {
            return f;
        }
        Calendar c = Calendar.getInstance();
        int slot = Math.min((c.get(Calendar.DAY_OF_YEAR) - 1) / SLOT_DAYS, CALENDAR.length - 1);
        return slot(c.get(Calendar.YEAR), slot);
    }

    /**
     * Event dates in UTC: RLC_SeasonalEventManager::getSeasonalEventTimeLeft(ToStart) compares them with
     * GameServerModule::getCurrentServerTimeUTC, and DateTime::fromISO8601 drops the offset (a local
     * "+01:00" date started the event one hour late). Incubator dates are the opposite (local).
     */
    static String utc(long millis) {
        java.text.SimpleDateFormat f = new java.text.SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss", java.util.Locale.US);
        f.setTimeZone(java.util.TimeZone.getTimeZone("UTC"));
        return f.format(new java.util.Date(millis)) + "+00:00";
    }

    /**
     * gameGlobals.versionTime of userprofile/meta: the game downloads the globals when it changes. The
     * whole calendar is sent at once, so it only changes with the covered years (or a forced event).
     */
    static String versionTime() {
        long[] f = forced();
        if (f != null) {
            return utc(f[1]);
        }
        Calendar c = Calendar.getInstance();
        c.clear();
        c.set(Calendar.YEAR, Calendar.getInstance().get(Calendar.YEAR));
        return utc(c.getTimeInMillis() + 1000L * CALENDAR_REVISION);
    }

    /** Bumped when the calendar's content changes, so that installed games download it again. */
    static final int CALENDAR_REVISION = 1;

    /** One override per event: the template fields, applied while its date condition is valid. */
    private static JSONObject override(long[] ev, boolean conditional) throws JSONException {
        JSONObject params = new JSONObject();
        params.put("currentSeasonalEventID2", (int) ev[0]);
        params.put("currentSeasonalEventStartingTime2", utc(ev[1]));
        params.put("currentSeasonalEventEndingTime2", utc(ev[2]));
        params.put("currentSeasonalEventCompleteEndingTime2", utc(ev[3]));
        // same shape as Ubisoft's overrides (gameglobals.isg.ckd): the template's fields + _CLASS_NAME
        params.put("_CLASS_NAME", "RLC_SeasonalEventManager_Template");
        JSONArray conditions = new JSONArray();
        if (conditional) {
            // online::GameGlobalsDateIntervalCondition, a factory object (SerializerJson: "_CLASS_NAME")
            JSONObject interval = new JSONObject();
            interval.put("_CLASS_NAME", "GameGlobalsDateIntervalCondition");
            interval.put("start", utc(ev[1]));
            interval.put("end", utc(ev[3]));
            interval.put("utc", true);
            conditions.put(interval);
        }
        JSONObject condition = new JSONObject();
        condition.put("conditions", conditions);
        condition.put("needAll", true);
        condition.put("priority", 0);
        condition.put("hotReload", true);
        JSONObject override = new JSONObject();
        override.put("json", params.toString());
        override.put("condition", condition);
        override.put("name", "seasonalEvent" + ev[0] + "_" + utc(ev[1]).substring(0, 10));
        return override;
    }

    /** GET v1/gameglobals/getGameGlobals: the calendar of YEARS years (or the forced event). */
    static JSONObject gameGlobals() throws JSONException {
        JSONArray overrides = new JSONArray();
        long[] f = forced();
        if (f != null) {
            overrides.put(override(f, false));
        } else {
            int year = Calendar.getInstance().get(Calendar.YEAR);
            for (int y = year; y < year + YEARS; y++) {
                for (int i = 0; i < CALENDAR.length; i++) {
                    overrides.put(override(slot(y, i), true));
                }
            }
        }
        JSONObject file = new JSONObject();
        file.put("overrides", overrides);
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
        long[] ev = current();
        Log.i(TAG, "seasonal events: " + overrides.length() + " override(s), now " + NAMES[(int) ev[0]]
                + " (id " + ev[0] + ") " + utc(ev[1]) + " -> " + utc(ev[2]) + " / " + utc(ev[3]));
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

    /** Forced event (admin), shared by all save slots: files/rlc/seasonal_forced.json. */
    private static java.io.File forcedFile() {
        return new java.io.File(OfflineServer.dataDir, "seasonal_forced.json");
    }

    private static JSONObject forcedState() {
        return Slots.read(forcedFile());
    }

    /** Admin: runs event id now for the given days (id 0 = back to the calendar). */
    static JSONObject force(int id, double days) throws JSONException {
        JSONObject s = forcedState();
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
        Slots.writeJson(forcedFile(), s);
        return gameGlobals();
    }
}
