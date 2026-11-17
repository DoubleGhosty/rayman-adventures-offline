package com.rayman.offline;

import org.json.JSONException;
import org.json.JSONObject;

import java.nio.charset.Charset;

/**
 * Developer endpoints of the embedded server, reachable from a PC with
 *   adb forward tcp:18080 tcp:18080
 *   curl http://127.0.0.1:18080/offline/admin/profile
 *   curl "http://127.0.0.1:18080/offline/admin/seedEgg?creatureId=2582585910&seconds=60"
 *   curl http://127.0.0.1:18080/offline/admin/state              (daily rewards, challenge scores)
 *   curl http://127.0.0.1:18080/offline/admin/resetDailyReward   (makes today's reward claimable again)
 *   curl http://127.0.0.1:18080/offline/admin/challenge          (today's challengeInfos)
 *   curl "http://127.0.0.1:18080/offline/admin/drawTickets?type=4&n=100000" (ticket draw histogram)
 *   curl "http://127.0.0.1:18080/offline/admin/forceTicket?type=9&e0=2" (next ticket = rare egg)
 *   curl "http://127.0.0.1:18080/offline/admin/miniEvent?name=Mini%20Marathon&hours=2" (runs a mini
 *                                                                 event now; name=auto: back to the schedule)
 *   curl "http://127.0.0.1:18080/offline/admin/seasonalEvent?id=3&days=7" (runs seasonal event 3 now; id=0:
 *                                                                 back to the calendar, SeasonalEvents.java)
 *   curl http://127.0.0.1:18080/offline/admin/ageChallenges      (moves stored scores one day back,
 *                                                                 to test the reward collection)
 * (the server only listens on the device loopback, so nothing else can reach it).
 */
final class Admin {

    private static final Charset UTF8 = Charset.forName("UTF-8");

    private Admin() {
    }

    static byte[] route(String method, String path, byte[] body) {
        synchronized (RlcApi.LOCK) {
            try {
                return routeInternal(path);
            } finally {
                OfflineServer.setStatus(200);   // Incubator.status() reports 410 when there is no egg
            }
        }
    }

    private static byte[] routeInternal(String path) {
        try {
            if (path.startsWith("/offline/admin/profile")) {
                return ProfileStore.get().toString(2).getBytes(UTF8);
            }
            if (path.startsWith("/offline/admin/incubation")) {
                return Incubator.status().toString(2).getBytes(UTF8);
            }
            if (path.startsWith("/offline/admin/state")) {
                return ServerState.get().toString(2).getBytes(UTF8);
            }
            if (path.startsWith("/offline/admin/resetDailyReward")) {
                ServerState.section("dailyRewards").remove("lastClaimDay");
                ServerState.save();
                return DailyRewards.getReward().toString(2).getBytes(UTF8);
            }
            if (path.startsWith("/offline/admin/drawTickets")) {
                int type = Integer.parseInt(param(path, "type", "3"));
                int n = Integer.parseInt(param(path, "n", "10000"));
                return Rewards.histogram(type, n).toString(2).getBytes(UTF8);
            }
            if (path.startsWith("/offline/admin/forceTicket")) {
                int type = Integer.parseInt(param(path, "type", "9"));
                Rewards.forced = Rewards.reward(type, Integer.parseInt(param(path, "count", "1")),
                        Integer.parseInt(param(path, "e0", "0")), Integer.parseInt(param(path, "e1", "0")), 0, 3,
                        "1".equals(param(path, "jackpot", "0")));
                return Rewards.forced.toString(2).getBytes(UTF8);
            }
            if (path.startsWith("/offline/admin/forceCharlie")) {
                Incubator.forceNextCharlie = true;
                return "{\"forceNextCharlie\":true}".getBytes(UTF8);
            }
            if (path.startsWith("/offline/admin/slots")) {
                return Slots.dump().toString(2).getBytes(UTF8);
            }
            if (path.startsWith("/offline/admin/miniEvent")) {
                String name = java.net.URLDecoder.decode(param(path, "name", "auto"), "UTF-8");
                double hours = Double.parseDouble(param(path, "hours", "1"));
                return MiniEvents.force(name, hours).toString(2).getBytes(UTF8);
            }
            if (path.startsWith("/offline/admin/seasonalEvent")) {
                int id = Integer.parseInt(param(path, "id", "0"));
                double days = Double.parseDouble(param(path, "days", "7"));
                return SeasonalEvents.force(id, days).toString(2).getBytes(UTF8);
            }
            if (path.startsWith("/offline/admin/ageChallenges")) {
                return Challenges.ageDays().toString(2).getBytes(UTF8);
            }
            if (path.startsWith("/offline/admin/challenge")) {
                return Challenges.getInfos().toString(2).getBytes(UTF8);
            }
            if (path.startsWith("/offline/admin/seedEgg")) {
                long creature = Long.parseLong(param(path, "creatureId", "2582585910"));
                long seconds = Long.parseLong(param(path, "seconds", "60"));
                JSONObject in = new JSONObject();
                in.put("creatureId", creature);
                in.put("eggAdventureSequence", ProfileStore.get().optLong("adventureCount", 0));
                in.put("eggAdventureRegion", 0);
                Incubator.startIncubation(in);
                JSONObject inc = ProfileStore.incubation();
                inc.put("hatchingEnd", Incubator.format(System.currentTimeMillis() + seconds * 1000));
                ProfileStore.save();
                return Incubator.status().toString(2).getBytes(UTF8);
            }
        } catch (JSONException | NumberFormatException | java.io.UnsupportedEncodingException e) {
            return ("{\"error\":\"" + e + "\"}").getBytes(UTF8);
        }
        return "{\"error\":\"unknown admin command\"}".getBytes(UTF8);
    }

    private static String param(String path, String name, String def) {
        int q = path.indexOf('?');
        if (q < 0) {
            return def;
        }
        for (String kv : path.substring(q + 1).split("&")) {
            int e = kv.indexOf('=');
            if (e > 0 && kv.substring(0, e).equals(name)) {
                return kv.substring(e + 1);
            }
        }
        return def;
    }
}
