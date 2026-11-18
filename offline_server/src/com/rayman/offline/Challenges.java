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
 *   leaderboard       {leaderboardRanges: [first, last] 0-based positions} -> challengeLeaderboardData
 *                     {entries[challengeScoreEntry]}
 *   setCollected      -> GameServerEmpty (rewards of the previous challenge taken)
 *
 * Offline the other players are fictional (FictionalPlayers): every day about 280 of them take part,
 * with scores spread around the player's usual score (the median of the player's best scores of the
 * previous days, fixed for the day when the player first plays it), so beating one's usual score
 * gives a good rank. The reward is the same at every rank (the ranking is for fun). A new challenge
 * starts every local day. During a marathon seasonal event the challenge is the event (the client
 * shows it in event mode) and its reward includes event currency.
 */
final class Challenges {

    private static final String TAG = OfflineServer.TAG;

    /** Token cap and refill time (our choice, the original values were server-side). */
    static final int TOKEN_COUNT = 5;
    static final int TOKEN_RECHARGE_SECONDS = 30 * 60;

    // RLC_RewardType values (see Rewards)
    private static final int REWARD_GEMS = 1;
    private static final int REWARD_LUCKY_TICKET = 3;
    private static final int REWARD_SEASONAL_CURRENCY = 16;

    /**
     * Event currency added to the reward during a marathon (our choice: Ubisoft's amounts per rank are
     * lost). With one run a day it pays a costume (2500) over the 23 days, plus tickets (60) and eggs
     * (350). The run itself also holds one currency pickup (client side, RLC_GS_Runner::
     * spawnSeasonalEventActors).
     */
    static final int MARATHON_CURRENCY = 150;

    /** Last rank of the last reward tier: every rank gets the reward. */
    private static final int ANY_RANK = 1000000;
    /** Score the fictional players are spread around before the player has a usual score. */
    private static final double FIRST_TYPICAL = 5000;

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
        long[] rank = pending >= 0 ? rank(pending) : new long[]{0, 0};
        out.put("challengeRank", rank[0]);
        out.put("challengeTotalPlayers", rank[1]);
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

    /**
     * online::challengeRewardList, sorted by maxRank: the client picks the first tier with rank <= maxRank.
     * The menu labels the first tier "RANG [minRank]" and the next ones "DE [minRank] A [maxRank]" or
     * "Top [maxPercent]%" (RLC_ChallengeManager::onRewardElementAppear): every rank gets the same
     * reward, shown as "1e" and "Top 100%".
     */
    private static JSONArray rewardTiers() throws JSONException {
        JSONArray tiers = new JSONArray();
        for (int[] range : new int[][]{{1, 1, 0}, {2, ANY_RANK, 100}}) {
            if (SeasonalEvents.marathonRunning()) {
                tiers.put(tier(range[0], range[1], range[2], reward(REWARD_SEASONAL_CURRENCY, MARATHON_CURRENCY),
                        reward(REWARD_GEMS, 25), reward(REWARD_LUCKY_TICKET, 1)));
            } else {
                tiers.put(tier(range[0], range[1], range[2], reward(REWARD_GEMS, 25), reward(REWARD_LUCKY_TICKET, 1)));
            }
        }
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
        if (!d.has("typical")) {
            d.put("typical", usualScore(today, score));
        }
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
        long[] rank = rank(ServerState.today());
        JSONObject out = new JSONObject();
        out.put("playerRank", rank[0]);
        out.put("totalPlayers", rank[1]);
        return out;
    }

    /** Median of the player's best scores before {@code day} ({@code fallback} if none). */
    private static double usualScore(long day, double fallback) {
        java.util.List<Double> bests = new java.util.ArrayList<>();
        Iterator<String> it = days().keys();
        while (it.hasNext()) {
            String k = it.next();
            JSONObject o = days().optJSONObject(k);
            try {
                if (o != null && o.has("best") && Long.parseLong(k) < day) {
                    bests.add(o.optDouble("best", 0));
                }
            } catch (NumberFormatException ignored) {
            }
        }
        if (bests.isEmpty()) {
            return fallback > 0 ? fallback : FIRST_TYPICAL;
        }
        java.util.Collections.sort(bests);
        return bests.get(bests.size() / 2);
    }

    /** The day's ranking, best first: {fictional player index (-1 = the player), score}. */
    private static java.util.List<long[]> ranking(long day) throws JSONException {
        JSONObject d = day(day, false);
        double typical = d != null && d.has("typical") ? d.getDouble("typical") : usualScore(day, 0);
        java.util.List<long[]> all = new java.util.ArrayList<>();
        for (int i = 0; i < FictionalPlayers.CHALLENGE; i++) {
            if (FictionalPlayers.hashOf(i, day) % 10 < 7) {          // about 7 in 10 play a given day
                all.add(new long[]{i, FictionalPlayers.scoreAround(i, day * 31 + 7, typical)});
            }
        }
        if (d != null && d.has("best")) {
            all.add(new long[]{-1, (long) d.getDouble("best")});
        }
        java.util.Collections.sort(all, (a, b) -> a[1] != b[1] ? Long.compare(b[1], a[1]) : Long.compare(a[0], b[0]));
        return all;
    }

    /** {player's rank (0: did not play), number of players} of a day. */
    private static long[] rank(long day) throws JSONException {
        java.util.List<long[]> all = ranking(day);
        for (int i = 0; i < all.size(); i++) {
            if (all.get(i)[0] < 0) {
                return new long[]{i + 1, all.size()};
            }
        }
        return new long[]{0, all.size()};
    }

    /**
     * leaderboard {leaderboardRanges}: the entries of the ranks asked for, as pairs of 0-based first and
     * last positions ([0, 9] = the top 10), else the top 10.
     */
    static JSONObject leaderboard(JSONObject in) throws JSONException {
        java.util.List<long[]> all = ranking(ServerState.today());
        java.util.TreeSet<Integer> ranks = new java.util.TreeSet<>();
        JSONArray asked = in.optJSONArray("leaderboardRanges");
        for (int i = 0; asked != null && i < asked.length(); i += 2) {
            int first = asked.optInt(i, 0);
            int last = i + 1 < asked.length() ? asked.optInt(i + 1, first) : first;
            for (int r = Math.max(0, first) + 1; r <= Math.min(last + 1, all.size()); r++) {
                ranks.add(r);
            }
        }
        if (ranks.isEmpty()) {
            for (int r = 1; r <= Math.min(10, all.size()); r++) {
                ranks.add(r);
            }
        }
        JSONObject p = ProfileStore.get();
        JSONArray entries = new JSONArray();
        for (int r : ranks) {
            long[] a = all.get(r - 1);
            JSONObject e = new JSONObject();
            if (a[0] < 0) {
                String pid = p.optString("pid", RlcApi.PLAYER_PID);
                e.put("name", p.optString("privateName", p.optString("name", "")));
                e.put("pid", pid);
                e.put("checkpid", pid);
                e.put("costume", p.optLong("costume", 0));
                e.put("img", p.optString("img", ""));
                e.put("country", p.optString("deviceCountry", ""));
            } else {
                FictionalPlayers.Player f = FictionalPlayers.get((int) a[0]);
                e.put("name", f.name);
                e.put("pid", f.pid);
                e.put("checkpid", f.pid);
                e.put("costume", f.costume);
                e.put("img", "");
                e.put("country", f.country);
            }
            e.put("score", a[1]);
            e.put("stars", 0);
            e.put("rank", r);
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
