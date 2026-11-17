package com.rayman.offline;

import org.json.JSONException;
import org.json.JSONObject;

import java.util.Calendar;

/**
 * Mini events ("v1/gameglobals/getMiniEventsStatus", RLC_MiniEventManager::onGameServerRequestDone).
 *
 *   answer: miniEventsStatus {currentMiniEventName, currentMiniEventStartingTime, currentMiniEventEndingTime}
 *
 * The game knows two events (RLC_MiniEventManager::getMiniEventTypeInString): "Mini Marathon" and
 * "Skull Scramble"; any other name (here "None") means no event. Everything else (intro popup,
 * notification, the event's bonus) is client-side. Ubisoft's calendar was server-side and is lost:
 * the schedule below is our choice - one event every weekend (Friday 00:00 to Monday 00:00, device
 * time), alternating between the two events from one week to the next.
 */
final class MiniEvents {

    static final String MINI_MARATHON = "Mini Marathon";
    static final String SKULL_SCRAMBLE = "Skull Scramble";
    static final String NONE = "None";
    private static final String NULL_DATE = "0000-00-00T00:00:00+00:00";

    private MiniEvents() {
    }

    static JSONObject status() throws JSONException {
        long now = System.currentTimeMillis();
        String name = NONE;
        long start = 0;
        long end = 0;
        JSONObject s = ServerState.section("miniEvents");
        if (s.has("forced") && s.optLong("forcedEnd", 0) > now) {
            name = s.getString("forced");
            start = s.optLong("forcedStart", now);
            end = s.getLong("forcedEnd");
        } else {
            Calendar c = Calendar.getInstance();
            c.setTimeInMillis(now);
            c.set(Calendar.HOUR_OF_DAY, 0);
            c.set(Calendar.MINUTE, 0);
            c.set(Calendar.SECOND, 0);
            c.set(Calendar.MILLISECOND, 0);
            // back to the Friday of this event window (Friday, Saturday, Sunday)
            int dow = c.get(Calendar.DAY_OF_WEEK);
            int back = dow == Calendar.FRIDAY ? 0 : dow == Calendar.SATURDAY ? 1 : dow == Calendar.SUNDAY ? 2 : -1;
            if (back >= 0) {
                c.add(Calendar.DAY_OF_MONTH, -back);
                start = c.getTimeInMillis();
                c.add(Calendar.DAY_OF_MONTH, 3);
                end = c.getTimeInMillis();
                long week = Math.floorDiv(ServerState.dayOf(start), 7L);
                name = week % 2 == 0 ? MINI_MARATHON : SKULL_SCRAMBLE;
            }
        }
        JSONObject out = new JSONObject();
        out.put("currentMiniEventName", name);
        out.put("currentMiniEventStartingTime", end > 0 ? Incubator.format(start) : NULL_DATE);
        out.put("currentMiniEventEndingTime", end > 0 ? Incubator.format(end) : NULL_DATE);
        return out;
    }

    /** Admin tool: runs an event now for the given hours ("auto" goes back to the schedule). */
    static JSONObject force(String name, double hours) throws JSONException {
        JSONObject s = ServerState.section("miniEvents");
        if (name.equals("auto")) {
            s.remove("forced");
            s.remove("forcedStart");
            s.remove("forcedEnd");
        } else {
            long now = System.currentTimeMillis();
            s.put("forced", name);
            s.put("forcedStart", now);
            s.put("forcedEnd", now + (long) (hours * 3600000));
        }
        ServerState.save();
        return status();
    }
}
