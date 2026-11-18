package com.rayman.offline;

import android.util.Log;

import org.json.JSONException;
import org.json.JSONObject;

import java.nio.charset.Charset;

/**
 * Emulation of the Rayman Adventures game server ("RLC" NodeJs API, base URL patched to
 * http://rc2.ubi.com in libuaf.so). Requests are {@code /v<N>/<module>/<action>} with a JSON body
 * serialized by the ITF engine; answers are deserialized with ITF SerializerJson (containers are
 * JSON arrays, maps are arrays of {"KEY":..,"VAL":..}).
 *
 * Responses must carry the "rlc-hash" header (RSA signature, verification patched out in libuaf)
 * and "rlc-time" (ISO-8601 server time). See docs/DOSSIER_TECHNIQUE.md for the endpoint table.
 */
final class RlcApi {

    private static final String TAG = OfflineServer.TAG;
    private static final Charset UTF8 = Charset.forName("UTF-8");

    static final String PLAYER_PID = "offline-player-0001";

    /** Reward of the last luckyTicket/getReward, echoed by the following consumeTicket. */
    private static JSONObject lastTicketReward;

    private RlcApi() {
    }

    static boolean handles(String path) {
        return path.matches("^/v\\d+/(userprofile|incubator|luckyTicket|dailyRewards|challenges|ghosts|"
                + "perks|messaging|gamefriends|deviceconfig|leaderboards|gameglobals|adsmanager|storepacks|"
                + "blocksounds)/.*");
    }

    /**
     * The client runs several connections at once; the server state (profile, incubator, last ticket
     * reward, state.json) is shared, so game requests are served one at a time.
     */
    static final Object LOCK = new Object();

    static byte[] route(String method, String path, byte[] body) {
        synchronized (LOCK) {
            return routeLocked(method, path, body);
        }
    }

    private static byte[] routeLocked(String method, String path, byte[] body) {
        String p = path;
        int q = p.indexOf('?');
        if (q >= 0) {
            p = p.substring(0, q);
        }
        String[] seg = p.split("/");  // "", "v1", module, action
        String module = seg.length > 2 ? seg[2] : "";
        String action = seg.length > 3 ? seg[3] : "";
        JSONObject in = parse(body);
        capture(method, module, action, body);
        try {
            if (module.equals("userprofile")) {
                if (action.equals("session")) {
                    return startSession(in);
                }
                if (action.equals("save")) {
                    // online::UpdateUserProfile: the client's full profile; becomes the server copy
                    ProfileStore.putUpload(in);
                    return empty();
                }
                if (action.equals("creatures")) {
                    return playerCreatures();
                }
            }
            if (module.equals("luckyTicket")) {
                // consumeTicket(ticketType) / getDecoyReward(ticketType, acquisition) / getVideoReward(type)
                // -> online::getRewardResult {"reward": RLC_LuckyTicketReward}
                // The client keeps (shows, then credits) the getReward answer; consumeTicket only
                // decrements the ticket count, and a valid creatureID in its answer would turn the
                // ticket into that egg (RLC_GS_LuckyTicket::onCurrentLuckyTicketConsumed): it echoes
                // the drawn reward instead of drawing a second one.
                int ticketType = in.optInt("ticketType", 3);
                JSONObject reward;
                if (action.equals("consumeTicket") && lastTicketReward != null) {
                    reward = lastTicketReward;
                    lastTicketReward = null;
                } else {
                    reward = Rewards.draw(ticketType, action.equals("getDecoyReward"));
                    if (action.equals("getReward")) {
                        lastTicketReward = reward;
                    }
                }
                Log.i(TAG, "luckyTicket/" + action + " (ticketType " + ticketType + ") -> " + reward);
                JSONObject out = new JSONObject();
                out.put("reward", reward);
                return out.toString().getBytes(UTF8);
            }
            if (module.equals("incubator")) {
                JSONObject out = null;
                if (action.equals("incubationStatus")) {
                    out = Incubator.status(in);
                } else if (action.equals("startIncubation")) {
                    out = Incubator.startIncubation(in);
                } else if (action.equals("useElixir")) {
                    out = Incubator.useElixir(in);
                } else if (action.equals("hatchingRitual") || action.equals("hatchCreature")) {
                    out = Incubator.hatch(in);
                } else if (action.equals("hatchSimulation")) {
                    out = Incubator.simulate(in);
                } else if (action.equals("magnifyingGlassNextAdventure")) {
                    out = Incubator.magnifyingGlass(in);
                } else if (action.equals("getCharlie")) {
                    out = Incubator.charlie(in);
                } else if (action.equals("timeSavingStatus")) {
                    // timeSavingStatusResult {timeLeft, status, end, type, name}: time-saving packs were
                    // paid subscriptions, none offline
                    out = new JSONObject();
                    out.put("timeLeft", 0);
                    out.put("status", 0);
                    out.put("end", "0000-00-00T00:00:00+00:00");
                    out.put("type", 0);
                    out.put("name", "");
                }
                if (out != null) {
                    return out.toString().getBytes(UTF8);
                }
            }
            JSONObject out = routeOther(module, action, in);
            if (out != null) {
                return out.toString().getBytes(UTF8);
            }
        } catch (JSONException e) {
            Log.e(TAG, "RLC " + module + "/" + action + " failed", e);
        }
        Log.w(TAG, "RLC endpoint not implemented yet: " + method + " " + module + "/" + action);
        return "{}".getBytes(UTF8);
    }

    /** Daily rewards, challenges and the endpoints that only need a well-formed answer. */
    private static JSONObject routeOther(String module, String action, JSONObject in) throws JSONException {
        if (module.equals("dailyRewards")) {
            if (action.equals("getReward")) {
                return DailyRewards.getReward();
            }
            if (action.equals("consumeReward")) {
                return DailyRewards.consumeReward();
            }
        }
        if (module.equals("challenges")) {
            if (action.equals("getInfos")) {
                return Challenges.getInfos();
            }
            if (action.equals("postChallenge")) {
                return Challenges.postChallenge(in);
            }
            if (action.equals("leaderboardConfig")) {
                return Challenges.leaderboardConfig();
            }
            if (action.equals("leaderboard")) {
                return Challenges.leaderboard();
            }
            if (action.equals("setCollected")) {
                return Challenges.setCollected();
            }
        }
        if (module.equals("ghosts")) {
            if (action.equals("uploadGhost")) {
                Ghosts.upload(in);
                return new JSONObject();
            }
            if (action.equals("getGhost")) {
                return Ghosts.get();
            }
        }
        if (module.equals("messaging") && action.startsWith("get_")) {
            // online::GameServer::Messaging::GetAll -> MessageList {messages[online::Message]}:
            // gifts and requests from friends, none offline
            JSONObject out = new JSONObject();
            out.put("messages", new org.json.JSONArray());
            return out;
        }
        if (module.equals("userprofile")) {
            if (action.equals("getPlayerCluster")) {
                // clusterNameResult {clusterName}: analytics / A-B population, none offline
                JSONObject out = new JSONObject();
                out.put("clusterName", "");
                return out;
            }
            if (action.equals("meta")) {
                return meta();
            }
            if (action.equals("unlinkSlot")) {
                return unlinkSlot(in);
            }
            if (action.equals("createLinkCode")) {
                return SaveCodes.createLinkCode(in);
            }
            if (action.equals("slot")) {
                return SaveCodes.linkSlot(in);
            }
            if (action.equals("getShortProfiles")) {
                return Leaderboards.shortProfiles(in);
            }
            if (action.equals("getUserProfile")) {
                return Leaderboards.userProfile();
            }
            if (action.equals("sns")) {
                return new JSONObject();    // social network ids, nothing to link offline
            }
        }
        if (module.equals("incubator") && action.equals("startNextAdventure")) {
            return new JSONObject();        // GameServerEmpty, the client starts the adventure timer itself
        }
        if (module.equals("leaderboards")) {
            return Leaderboards.route(action, in);
        }
        if (module.equals("gameglobals") && action.equals("getMiniEventsStatus")) {
            return MiniEvents.status();
        }
        if (module.equals("gameglobals") && action.equals("getGameGlobals")) {
            return SeasonalEvents.gameGlobals();      // seasonal event calendar (template override)
        }
        if (module.equals("storepacks") && action.equals("packs")) {
            // getStorePacksResult {packs[RLC_StorePacksLocInfo]}: localized texts of paid packs, none offline
            JSONObject out = new JSONObject();
            out.put("packs", new org.json.JSONArray());
            return out;
        }
        if (module.equals("blocksounds")) {
            // blockedsoundsResult {blockedsounds[String8]}: sounds muted remotely, none
            JSONObject out = new JSONObject();
            out.put("blockedsounds", new org.json.JSONArray());
            return out;
        }
        if (module.equals("adsmanager")) {
            // adsManagerResult {campaigns[adsCampaign]}: no ad campaigns offline
            JSONObject out = new JSONObject();
            out.put("campaigns", new org.json.JSONArray());
            return out;
        }
        if (module.equals("userprofile") && (action.equals("logiap") || action.equals("registerNewCreature")
                || action.equals("registerTimeSaving") || action.equals("registerActivatePerk")
                || action.equals("stat") || action.equals("onBoardingFinished") || action.equals("ping"))) {
            // purchase logs (real-money IAP, unreachable offline), statistics, onboarding flag and the
            // "should the game restart" ping: nothing to report back
            return new JSONObject();
        }
        if (module.equals("perks") || module.equals("gamefriends") || module.equals("deviceconfig")) {
            // perks = paid bonus packs, gamefriends = Facebook friends, deviceconfig = per-device
            // overrides: nothing exists offline, an empty answer is what the client expects then
            return new JSONObject();
        }
        return null;
    }

    /** Save slots of the title screen "Sauvegardes" menu (RO2_GS_MainMenu::initialiseSaveSlots). */
    static final int SAVE_SLOTS = 3;

    /**
     * POST v1/userprofile/meta {token} -> online::MetaInfo {gameGlobals {versionTime, branch},
     * slots[Slot {pid, username, save, saveUniqueId, saveUbiId, adventureCount, creatureCount, lastPlay,
     * version, compatible}]}: the account's save slots (Slots.java). RO2_GS_MainMenu::initialiseSaveSlots
     * reads slots[0..2] without checking the list size, so the answer always holds three slots (an empty
     * answer crashed the game, SIGSEGV in String8::operator=).
     */
    private static JSONObject meta() throws JSONException {
        JSONObject gg = new JSONObject();
        gg.put("versionTime", SeasonalEvents.versionTime());   // a new value makes the game fetch getGameGlobals
        gg.put("branch", 0);
        org.json.JSONArray slots = new org.json.JSONArray();
        for (int i = 0; i < SAVE_SLOTS; i++) {
            String pid = Slots.pidAt(i);
            JSONObject p = pid.isEmpty() ? new JSONObject() : ProfileStore.of(pid);
            boolean used = !pid.isEmpty();
            JSONObject s = new JSONObject();
            s.put("pid", pid);
            String name = p.optString("name", "");
            s.put("username", name.isEmpty() ? p.optString("privateName", "") : name);
            s.put("save", used);
            s.put("saveUniqueId", p.optLong("saveUniqueId", 0));
            s.put("saveUbiId", p.optString("saveUbiId", ""));
            s.put("adventureCount", p.optLong("adventureCount", 0));
            s.put("creatureCount", 0);
            s.put("lastPlay", p.optString("universeLastUpdate", "0000-00-00T00:00:00+00:00"));
            s.put("version", p.optString("gameVersion", ""));
            s.put("compatible", true);
            slots.put(s);
        }
        JSONObject out = new JSONObject();
        out.put("gameGlobals", gg);
        out.put("slots", slots);
        return out;
    }

    /**
     * POST v1/userprofile/unlinkSlot SaveIdentifier {pid, slot} (red bin of the "Sauvegardes" menu): the
     * slot becomes free. The player's server files are kept on the device (nothing is deleted).
     */
    private static JSONObject unlinkSlot(JSONObject in) throws JSONException {
        long slot = in.optLong("slot", Slots.NO_SLOT);
        String pid = in.optString("pid", "");
        int i = slot >= 0 && slot < SAVE_SLOTS ? (int) slot : Slots.indexOf(pid);
        if (i >= 0) {
            Log.i(TAG, "slots: slot " + i + " (" + Slots.pidAt(i) + ") unlinked");
            Slots.assign(i, "");
        }
        return new JSONObject();
    }

    /**
     * POST v1/userprofile/session SessionParams {pid, slot, localSave, saveUniqueId, adventureCount}
     * -> online::SaveInfo {pid, slot, saveUniqueId, forceNewGame, save, msdkData, ...}.
     * Requests seen (Sauvegardes menu, see Slots.java):
     *   normal start           {pid: current, slot: none, localSave: true}  -> the local game goes on
     *   "Nouvelle partie" in N {pid: "", slot: N, localSave: false}         -> new pid + forceNewGame
     *   play an existing slot  {pid: P, slot: none, localSave: false, lastPid, lastUniverse}
     *                          -> P's stored save; lastUniverse (base64 save of the game being left,
     *                          same format as the upload's "save") is stored as lastPid's save.
     */
    private static byte[] startSession(JSONObject in) throws JSONException {
        long slot = in.optLong("slot", Slots.NO_SLOT);
        String reqPid = in.optString("pid", "");
        boolean localSave = in.optBoolean("localSave", true);
        String pid;
        boolean newGame = false;
        String save = "";
        long saveId = in.optLong("saveUniqueId", 1);
        int format = 0;
        String lastPid = in.optString("lastPid", "");
        String lastUniverse = in.optString("lastUniverse", "");
        if (!lastPid.isEmpty() && !lastUniverse.isEmpty() && Slots.indexOf(lastPid) >= 0) {
            ProfileStore.storeSave(lastPid, lastUniverse);
            Log.i(TAG, "slots: game of " + lastPid + " kept (" + lastUniverse.length() + " chars)");
        }
        if ((slot < 0 || slot >= SAVE_SLOTS) && !localSave && !reqPid.isEmpty()
                && !reqPid.equals(Slots.current()) && Slots.indexOf(reqPid) >= 0) {
            JSONObject p = ProfileStore.of(reqPid);
            pid = reqPid;
            save = p.optString("save", "");
            saveId = p.optLong("saveUniqueId", 1);
            format = p.optInt("saveVersionFormat", 0);
            Slots.setCurrent(pid);
            Log.i(TAG, "slots: load " + pid + " (" + save.length() + " chars of save)");
        } else if (slot < 0 || slot >= SAVE_SLOTS) {
            pid = reqPid.isEmpty() ? Slots.current() : reqPid;
            Slots.setCurrent(pid);
        } else {
            String owner = Slots.pidAt((int) slot);
            if (owner.isEmpty()) {
                pid = Slots.newPid();
                Slots.assign((int) slot, pid);
                Slots.setCurrent(pid);
                newGame = true;
                saveId = 1;
                Log.i(TAG, "slots: new game in slot " + slot + " (" + pid + ")");
            } else if (owner.equals(Slots.current())) {
                pid = owner;
                Log.i(TAG, "slots: slot " + slot + " is the current game (" + pid + ")");
            } else {
                JSONObject p = ProfileStore.of(owner);
                pid = owner;
                save = p.optString("save", "");
                saveId = p.optLong("saveUniqueId", 1);
                format = p.optInt("saveVersionFormat", 0);
                Slots.setCurrent(pid);
                Log.i(TAG, "slots: load slot " + slot + " (" + pid + ", " + save.length() + " chars of save)");
            }
        }
        JSONObject out = new JSONObject();
        out.put("pid", pid);
        int idx = Slots.indexOf(pid);
        out.put("slot", idx < 0 ? 0 : idx);
        out.put("saveUniqueId", saveId == Slots.NO_SLOT ? 1 : saveId);
        out.put("forceNewGame", newGame);
        out.put("save", save);
        out.put("msdkData", "");
        out.put("saveGameVersionFormat", format);
        out.put("populations", new org.json.JSONArray());
        out.put("iap", false);
        out.put("iapPrediction", 0);
        out.put("reco", new org.json.JSONArray());
        return out.toString().getBytes(UTF8);
    }

    /** Keeps the last request body of every endpoint in files/rlc/capture/ (reverse-engineering aid). */
    private static void capture(String method, String module, String action, byte[] body) {
        if (OfflineServer.dataDir == null) {
            return;
        }
        java.io.File dir = new java.io.File(OfflineServer.dataDir, "capture");
        dir.mkdirs();
        try {
            java.io.FileOutputStream fo = new java.io.FileOutputStream(
                    new java.io.File(dir, method + "_" + module + "_" + action + ".json"));
            try {
                fo.write(body == null ? new byte[0] : body);
            } finally {
                fo.close();
            }
        } catch (java.io.IOException e) {
            Log.w(TAG, "capture failed", e);
        }
    }

    /** GET v1/userprofile/creatures -> online::PlayerCreatureList, served from the stored profile. */
    private static byte[] playerCreatures() throws JSONException {
        JSONObject p = ProfileStore.get();
        JSONObject out = new JSONObject();
        out.put("creatures", p.has("creatures") ? p.getJSONArray("creatures") : new org.json.JSONArray());
        out.put("incubationData", ProfileStore.incubation());
        // RLC_AdventureManager only calls RLC_CreatureManager::reconcileServerCreatures (which replaces
        // the local creatures with this list, saves and forces a restart, error 0x10010601) when this
        // id is empty or equal to the local pid. The real creatures live in the encrypted local save
        // (the upload's "creatures" field is empty), so a distinct id keeps the local data authoritative.
        out.put("profileId", "offline-server");
        out.put("iapScore", p.optLong("iapScore", 0));
        out.put("joinDate", p.optString("joinDate", ""));
        out.put("devTeam", false);
        out.put("onBoardingFinished", true);
        return out.toString().getBytes(UTF8);
    }

    private static byte[] empty() {
        return "{}".getBytes(UTF8);
    }

    private static JSONObject parse(byte[] body) {
        if (body == null || body.length == 0) {
            return new JSONObject();
        }
        try {
            return new JSONObject(new String(body, UTF8));
        } catch (JSONException e) {
            return new JSONObject();
        }
    }
}
