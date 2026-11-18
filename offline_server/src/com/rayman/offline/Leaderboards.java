package com.rayman.offline;

import android.util.Log;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

/**
 * World / friends leaderboards ("v1/leaderboards/*", online::GameServer::Leaderboards, handled by
 * RLC_LeaderboardManager; the "tree" ranking and the per-map scores).
 *
 *   postLeaderboard PostRequest {is_map, map_id, score, is_time_attack, map_seed} -> (nothing read back)
 *   getLeaderboard  GetRequest {is_map, map_id, players_type (World/Country/Friends), select_type
 *                   (Best/Range/Random...), start, count, rank}
 *                   -> ScoreList {scores[ScoreEntry {player, score}], rank PlayerRank {score, rank, percent}}
 *
 *   userprofile/getShortProfiles userProfileIdList {profileId[]} -> userProfileShortList
 *                   {profiles[userProfileShortData {pid, name, deviceCountry, stars, costume, img}]}
 *   userprofile/getUserProfile   userProfileId {profileId} -> userProfileOtherData (the uploaded profile)
 *
 * The tree ranking ("Classement": is_map false, map_id 0xFFFFFFFF) is a ranking of the stars of the
 * players' Incrediballs (RLC_LeaderboardManager::computeNewPlayersScoreListInRange reads
 * RLC_CreatureManager::getStarsTotalNb): "Best" = the top players, "Range" = the players whose stars
 * are in [start, start + count) (zones of 15 stars up to the player's own), "Random" = a sample. The
 * client places the player from its own data and asks with rank false.
 *
 * Offline the rankings are filled with fictional players (FictionalPlayers): World = all of them,
 * Country = the ones of the player's country, Friends = the player alone (no friends offline). The
 * map rankings put them around the player's own best score on that map (this version of the client
 * only posts map scores: RLC_LeaderboardManager only asks for the tree ranking). The player's best
 * scores are kept in state.json ("leaderboards").
 */
final class Leaderboards {

    private static final String TAG = OfflineServer.TAG;

    private Leaderboards() {
    }

    private static String key(JSONObject in) {
        return (in.optBoolean("is_map", false) ? "map" : "global") + "_" + in.optLong("map_id", 4294967295L)
                + (in.optBoolean("is_time_attack", false) ? "_ta" : "");
    }

    static JSONObject route(String action, JSONObject in) throws JSONException {
        JSONObject s = ServerState.section("leaderboards");
        if (action.equals("postLeaderboard")) {
            String k = key(in);
            double score = in.optDouble("score", 0);
            boolean timeAttack = in.optBoolean("is_time_attack", false);
            boolean better = !s.has(k) || (timeAttack ? score < s.getDouble(k) : score > s.getDouble(k));
            if (better) {
                s.put(k, score);
                ServerState.save();
            }
            Log.i(TAG, "leaderboard " + k + ": score " + score + (better ? " (best)" : ""));
            return new JSONObject();
        }
        // getLeaderboard (and anything else of the module)
        String k = key(in);
        boolean isMap = in.optBoolean("is_map", false);
        boolean timeAttack = in.optBoolean("is_time_attack", false);
        String type = in.optString("players_type", "World");
        String select = in.optString("select_type", "Best");
        int start = Math.max(0, in.optInt("start", 0));
        int count = Math.max(1, Math.min(100, in.optInt("count", 10)));
        boolean has = s.has(k);
        double mine = s.optDouble(k, 0);

        // everyone of this ranking: {index (-1 = the player), score}, best first
        List<long[]> all = new ArrayList<>();
        if (!type.equals("Friends")) {
            String country = FictionalPlayers.playerCountry();
            long salt = in.optLong("map_id", 0) * 2 + (timeAttack ? 1 : 0);
            double typical = has && mine > 0 ? mine : 500;
            for (FictionalPlayers.Player p : FictionalPlayers.world()) {
                if (type.equals("Country") && !p.country.equals(country)) {
                    continue;
                }
                if (isMap && FictionalPlayers.hashOf(p.index, salt) % 3 == 0) {
                    continue;           // not everybody played every map
                }
                long score = isMap ? FictionalPlayers.scoreAround(p.index, salt, typical)
                        : FictionalPlayers.treeStars(p.index);
                all.add(new long[]{p.index, score});
            }
        }
        if (has && (isMap || type.equals("Friends"))) {
            all.add(new long[]{-1, Math.round(mine)});    // the tree ranking places the player itself
        }
        Collections.sort(all, (a, b) -> timeAttack ? Long.compare(a[1], b[1]) : Long.compare(b[1], a[1]));

        List<long[]> page = new ArrayList<>();
        if (select.equals("Range") && !isMap) {
            List<long[]> zone = new ArrayList<>();
            for (long[] e : all) {
                if (e[1] >= start && e[1] < (long) start + count) {
                    zone.add(e);
                }
            }
            for (int i = 0; i < Math.min(count, zone.size()); i++) {      // spread over the zone
                page.add(zone.get(i * zone.size() / Math.min(count, zone.size())));
            }
        } else if (select.equals("Range")) {
            for (int i = start; i < Math.min(all.size(), start + count); i++) {
                page.add(all.get(i));
            }
        } else if (select.equals("Random")) {
            List<long[]> shuffled = new ArrayList<>(all);
            Collections.shuffle(shuffled, new java.util.Random(ServerState.today() * 31 + k.hashCode()));
            page.addAll(shuffled.subList(0, Math.min(count, shuffled.size())));
        } else {
            page.addAll(all.subList(0, Math.min(count, all.size())));
        }
        if (page.isEmpty() && type.equals("Friends") && start == 0) {
            page.add(new long[]{-1, Math.round(mine)});   // never an empty answer (see the class comment)
        }

        JSONArray scores = new JSONArray();
        for (long[] e : page) {
            JSONObject entry = new JSONObject();
            entry.put("player", e[0] < 0 ? playerId() : FictionalPlayers.PID_PREFIX + e[0]);
            entry.put("score", e[1]);
            scores.put(entry);
        }
        long better = 0;
        for (long[] e : all) {
            if (e[0] >= 0 && (timeAttack ? e[1] < mine : e[1] > mine)) {
                better++;
            }
        }
        JSONObject out = new JSONObject();
        out.put("scores", scores);
        JSONObject rank = new JSONObject();
        rank.put("score", mine);
        rank.put("rank", better + 1);
        rank.put("percent", 100.0 * (better + 1) / (all.size() + (has ? 0 : 1)));
        out.put("rank", rank);
        return out;
    }

    static String playerId() {
        return ProfileStore.get().optString("pid", RlcApi.PLAYER_PID);
    }

    /** userprofile/getShortProfiles: the cards of the player and of the fictional players asked for. */
    static JSONObject shortProfiles(JSONObject in) throws JSONException {
        JSONObject p = ProfileStore.get();
        JSONArray ids = in.optJSONArray("profileId");
        JSONArray profiles = new JSONArray();
        String me = playerId();
        for (int i = 0; ids != null && i < ids.length(); i++) {
            String id = ids.optString(i);
            if (me.equals(id)) {
                profiles.put(shortProfile(p));
            } else if (FictionalPlayers.isFictional(id) && FictionalPlayers.byPid(id) != null) {
                profiles.put(FictionalPlayers.byPid(id).shortProfile());
            }
        }
        if (ids == null) {
            profiles.put(shortProfile(p));
        }
        JSONObject out = new JSONObject();
        out.put("profiles", profiles);
        return out;
    }

    private static JSONObject shortProfile(JSONObject p) throws JSONException {
        JSONObject o = new JSONObject();
        o.put("pid", playerId());
        String name = p.optString("name", "");
        o.put("name", name.isEmpty() ? p.optString("privateName", "") : name);
        o.put("deviceCountry", p.optString("deviceCountry", ""));
        o.put("stars", p.optLong("stars", 0));
        o.put("costume", p.optLong("costume", 0));
        o.put("img", p.optString("img", ""));
        return o;
    }

    /**
     * userprofile/getUserProfile {profileId}: the stored profile (without the encrypted save blob), or the
     * card of a fictional player with Incrediballs worth their stars.
     */
    static JSONObject userProfile(JSONObject in) throws JSONException {
        String id = in.optString("profileId", "");
        if (FictionalPlayers.isFictional(id) && FictionalPlayers.byPid(id) != null) {
            JSONObject o = FictionalPlayers.byPid(id).shortProfile();
            o.put("privateName", o.getString("name"));
            o.put("creatures", FictionalPlayers.creatures(FictionalPlayers.byPid(id).index));
            return o;
        }
        JSONObject p = new JSONObject(ProfileStore.get().toString());
        p.remove("save");
        JSONObject sp = shortProfile(p);
        p.put("name", sp.getString("name"));
        return p;
    }
}
