package com.rayman.offline;

import android.util.Log;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

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
 * Offline the player is alone: every list holds the player only (1st of 1). The list must not be
 * empty - RLC_GS_Leaderboard::initialiseOnlineProfiles shows "Echec de la connexion au serveur" when
 * the answers carry no player id. The player's best scores are kept in state.json ("leaderboards").
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
        double score = s.optDouble(k, 0);
        JSONObject entry = new JSONObject();
        entry.put("player", playerId());
        entry.put("score", score);
        JSONArray scores = new JSONArray();
        if (in.optLong("start", 0) == 0) {
            scores.put(entry);      // later pages ("Range" start > 0) are empty: there is nobody else
        }
        JSONObject out = new JSONObject();
        out.put("scores", scores);
        JSONObject rank = new JSONObject();
        rank.put("score", score);
        rank.put("rank", 1);
        rank.put("percent", 100.0);
        out.put("rank", rank);
        return out;
    }

    static String playerId() {
        return ProfileStore.get().optString("pid", RlcApi.PLAYER_PID);
    }

    /** userprofile/getShortProfiles: the player's own card for every requested id that is theirs. */
    static JSONObject shortProfiles(JSONObject in) throws JSONException {
        JSONObject p = ProfileStore.get();
        JSONArray ids = in.optJSONArray("profileId");
        JSONArray profiles = new JSONArray();
        String me = playerId();
        for (int i = 0; ids != null && i < ids.length(); i++) {
            if (me.equals(ids.optString(i))) {
                profiles.put(shortProfile(p));
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

    /** userprofile/getUserProfile: the stored profile (without the encrypted save blob). */
    static JSONObject userProfile() throws JSONException {
        JSONObject p = new JSONObject(ProfileStore.get().toString());
        p.remove("save");
        JSONObject sp = shortProfile(p);
        p.put("name", sp.getString("name"));
        return p;
    }
}
