package com.rayman.offline;

import android.util.Log;

import org.json.JSONException;
import org.json.JSONObject;

/**
 * "v1/dailyRewards/*" (online::dailyRewardsModule, handled by RLC_SocialManager).
 *
 *   getReward     -> getDailyRewardResult {"reward": uint}. Non-zero = a daily reward is available:
 *                    RLC_SocialManager then opens the daily reward menu. The reward itself (food,
 *                    gems...) comes from the client's own config (RLC_InAppPurchaseManager::getDailyRewards).
 *   consumeReward -> GameServerEmpty; the client then credits the reward (giveDailyReward).
 *
 * One reward per local calendar day.
 */
final class DailyRewards {

    private static final String TAG = OfflineServer.TAG;

    private DailyRewards() {
    }

    static JSONObject getReward() throws JSONException {
        JSONObject s = ServerState.section("dailyRewards");
        boolean available = s.optLong("lastClaimDay", -1) != ServerState.today();
        JSONObject out = new JSONObject();
        out.put("reward", available ? 1 : 0);
        return out;
    }

    static JSONObject consumeReward() throws JSONException {
        JSONObject s = ServerState.section("dailyRewards");
        long today = ServerState.today();
        long last = s.optLong("lastClaimDay", -1);
        s.put("streak", last == today - 1 ? s.optInt("streak", 0) + 1 : 1);
        s.put("lastClaimDay", today);
        s.put("claims", s.optInt("claims", 0) + 1);
        ServerState.save();
        Log.i(TAG, "dailyRewards: claimed for day " + today);
        return new JSONObject();
    }
}
