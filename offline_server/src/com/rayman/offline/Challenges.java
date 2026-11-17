package com.rayman.offline;

import android.util.Log;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.util.Iterator;

/**
 * Daily challenge ("v1/challenges/*", online::rlcChallengesModule, handled by RLC_ChallengeManager).
 *
 *   getInfos          -> online::challengeInfos {seed, timeLeft, eventTimeLeft, thresholds,
 *                        difficultyThresholds, continueParams, mapPath, configPath, disabledBricks,
 *                        leaderboardRewards[challengeRewardList], canCollect, challengeRank,
 *                        challengeDate, challengeTotalPlayers, tokenCount, tokenRechargeTimer}
 *                        Empty mapPath/configPath/thresholds make the client fall back to its
 *                        RLC_ChallengeManager template (World/challenge/Run/ChallengeRun) and to
 *                        thresholds drawn from the seed, so the server only drives seed and timing.
 *                        tokenCount is the token cap, tokenRechargeTimer the seconds per token; the
 *                        refill itself is done by the client.
 *   postChallenge     {score} -> challengeScoreResult {updated}
 *   leaderboardConfig -> challengeLeaderboardConfig {playerRank, totalPlayers}
 *   leaderboard       {leaderboardRanges} -> challengeLeaderboardData {entries[challengeScoreEntry]}
 *   setCollected      -> GameServerEmpty (rewards of the previous challenge taken)
 *
 * Offline there are no other players: the leaderboard holds the player alone, so a played challenge
 * always ends at rank 1/1. A new challenge starts every local day.
 */
final class Challenges {

    private static final String TAG = OfflineServer.TAG;

    /** Token cap and refill time (our choice, the original values were server-side). */
    static final int TOKEN_COUNT = 5;
    static final int TOKEN_RECHARGE_SECONDS = 30 * 60;

    // RLC_RewardType values (see Rewards)
    private static final int REWARD_GEMS = 1;
    private static final int REWARD_LUCKY_TICKET = 3;

    private Challenges() {
    }

    private static JSONObject days() {
        JSONObject c = ServerState.section("challenges");
        JSONObject d = c.optJSONObject("days");
        if (d == null) {
            d = new JSONObject();
            try {
                c.put("days", d);
            } catch (JSONException ignored) {
            }
        }
        return d;
    }

    private static JSONObject day(long day, boolean create) throws JSONException {
        JSONObject d = days().optJSONObject(Long.toString(day));
        if (d == null && create) {
            d = new JSONObject();
            days().put(Long.toString(day), d);
        }
        return d;
    }

    /** Seed of a day's challenge (anything but 0xFFFFFFFF, which means "no challenge"). */
    static long seed(long day) {
        return ((day * 2654435761L) ^ 0x5DEECE66DL) & 0x7FFFFFFFL;
    }

    static JSONObject getInfos() throws JSONException {
        long today = ServerState.today();
        JSONObject out = new JSONObject();
        out.put("seed", seed(today));
        out.put("timeLeft", (double) ServerState.secondsToNextDay());
        out.put("eventTimeLeft", 0.0);
        out.put("thresholds", new JSONArray());
        out.put("difficultyThresholds", new JSONArray());
        out.put("continueParams", new JSONArray());
        out.put("mapPath", "");
        out.put("configPath", "");
        out.put("disabledBricks", new JSONArray());
        out.put("leaderboardRewards", rewardTiers());

        long pending = pendingCollectDay(today);
        out.put("canCollect", pending >= 0);
        out.put("challengeRank", pending >= 0 ? 1 : 0);
        out.put("challengeTotalPlayers", pending >= 0 ? 1 : 0);
        out.put("challengeDate", Incubator.format(ServerState.dayStart(pending >= 0 ? pending : today)));

        out.put("tokenCount", TOKEN_COUNT);
        out.put("tokenRechargeTimer", TOKEN_RECHARGE_SECONDS);
        return out;
    }

    /** Most recent past challenge the player took part in and whose reward was not collected (-1: none). */
    private static long pendingCollectDay(long today) {
        long best = -1;
        Iterator<String> it = days().keys();
        while (it.hasNext()) {
            String k = it.next();
            long d;
            try {
                d = Long.parseLong(k);
            } catch (NumberFormatException e) {
                continue;
            }
            JSONObject o = days().optJSONObject(k);
            if (d < today && o != null && o.has("best") && !o.optBoolean("collected", false) && d > best) {
                best = d;
            }
        }
        return best;
    }

    /** online::challengeRewardList, sorted by maxRank: the client picks the first tier with rank <= maxRank. */
    private static JSONArray rewardTiers() throws JSONException {
        JSONArray tiers = new JSONArray();
        tiers.put(tier(1, 1, 0, reward(REWARD_GEMS, 25), reward(REWARD_LUCKY_TICKET, 1)));
        return tiers;
    }

    private static JSONObject tier(int minRank, int maxRank, int maxPercent, JSONObject... rewards)
            throws JSONException {
        JSONObject t = new JSONObject();
        t.put("maxRank", maxRank);
        t.put("minRank", minRank);
        JSONArray r = new JSONArray();
        for (JSONObject o : rewards) {
            r.put(o);
        }
        t.put("rewards", r);
        t.put("maxPercent", maxPercent);
        return t;
    }

    private static JSONObject reward(int type, int count) throws JSONException {
        JSONObject r = new JSONObject();
        r.put("type", type);
        r.put("count", count);
        r.put("elixirType", 0);
        r.put("costumeName", "");
        return r;
    }

    static JSONObject postChallenge(JSONObject in) throws JSONException {
        double score = in.optDouble("score", 0);
        long today = ServerState.today();
        JSONObject d = day(today, true);
        boolean updated = !d.has("best") || score > d.getDouble("best");
        if (updated) {
            d.put("best", score);
        }
        d.put("plays", d.optInt("plays", 0) + 1);
        ServerState.save();
        Log.i(TAG, "challenge: score " + score + " for day " + today + (updated ? " (new best)" : ""));
        JSONObject out = new JSONObject();
        out.put("updated", updated);
        return out;
    }

    static JSONObject leaderboardConfig() throws JSONException {
        JSONObject d = day(ServerState.today(), false);
        boolean played = d != null && d.has("best");
        JSONObject out = new JSONObject();
        out.put("playerRank", played ? 1 : 0);
        out.put("totalPlayers", played ? 1 : 0);
        return out;
    }

    static JSONObject leaderboard() throws JSONException {
        JSONArray entries = new JSONArray();
        JSONObject d = day(ServerState.today(), false);
        if (d != null && d.has("best")) {
            JSONObject p = ProfileStore.get();
            JSONObject e = new JSONObject();
            String pid = p.optString("pid", RlcApi.PLAYER_PID);
            e.put("name", p.optString("privateName", p.optString("name", "")));
            e.put("pid", pid);
            e.put("checkpid", pid);
            e.put("score", (long) d.getDouble("best"));
            e.put("stars", 0);
            e.put("costume", p.optLong("costume", 0));
            e.put("img", p.optString("img", ""));
            e.put("country", p.optString("deviceCountry", ""));
            e.put("rank", 1);
            entries.put(e);
        }
        JSONObject out = new JSONObject();
        out.put("entries", entries);
        return out;
    }

    /** Test helper: every stored challenge moves one day into the past. */
    static synchronized JSONObject ageDays() throws JSONException {
        JSONObject old = days();
        JSONObject aged = new JSONObject();
        Iterator<String> it = old.keys();
        while (it.hasNext()) {
            String k = it.next();
            try {
                aged.put(Long.toString(Long.parseLong(k) - 1), old.get(k));
            } catch (NumberFormatException ignored) {
            }
        }
        ServerState.section("challenges").put("days", aged);
        ServerState.save();
        return ServerState.get();
    }

    static JSONObject setCollected() throws JSONException {
        long today = ServerState.today();
        Iterator<String> it = days().keys();
        while (it.hasNext()) {
            String k = it.next();
            JSONObject o = days().optJSONObject(k);
            try {
                if (o != null && Long.parseLong(k) < today) {
                    o.put("collected", true);
                }
            } catch (NumberFormatException ignored) {
            }
        }
        ServerState.save();
        Log.i(TAG, "challenge: rewards collected");
        return new JSONObject();
    }
}
