package com.rayman.offline;

import android.util.Log;

import org.json.JSONException;
import org.json.JSONObject;

import java.io.File;
import java.security.SecureRandom;

/**
 * Save codes of the title screen "Sauvegardes" menu ("code de sauvegarde").
 *
 * Ubisoft's server attached a player's save to another device's slot with a short-lived code:
 *   POST v1/userprofile/createLinkCode  SaveIdentifier {pid, slot}
 *        -> online::LinkCode {slot, profileId, code, ttl}   (RO2_GS_MainMenu::createLinkCode; the game
 *           shows the code and its validity)
 *   PUT  v1/userprofile/slot            SlotLinkParams = LinkCode {slot, profileId, code, ttl} + token
 *        -> GameServerEmpty, then the game asks userprofile/meta again and the slot shows the save;
 *           HTTP 404 = unknown code (RO2_GS_MainMenu::onGameServerRequestDone, message 0x281).
 *
 * Offline the server lives in the app, so a code can only be used on the device that made it. It is
 * a copy: creating the code takes a snapshot of the player's server files (profile with the last
 * uploaded save, server state, ghost) in files/rlc/codes/CODE/, and entering it in a slot creates a
 * new player there from that snapshot. Useful to duplicate a game into another slot, or to keep a
 * restore point. Codes are 6 digits and stay valid 7 days (the game shows "10080 minutes"); expired
 * snapshots are deleted when a new code is made.
 */
final class SaveCodes {

    private static final String TAG = OfflineServer.TAG;
    /** Server files of a player that make up a game (Slots.fileFor). */
    private static final String[] FILES = {"profile.json", "state.json", "ghost.json"};
    /** Validity in seconds (the game shows it in minutes). */
    static final int TTL = 7 * 24 * 3600;

    private static final SecureRandom RANDOM = new SecureRandom();

    private SaveCodes() {
    }

    private static File dir() {
        File d = new File(OfflineServer.dataDir, "codes");
        d.mkdirs();
        return d;
    }

    static synchronized JSONObject createLinkCode(JSONObject in) throws JSONException {
        long slot = in.optLong("slot", Slots.NO_SLOT);
        String pid = in.optString("pid", "");
        if (pid.isEmpty() && slot >= 0 && slot < Slots.COUNT) {
            pid = Slots.pidAt((int) slot);
        }
        JSONObject out = new JSONObject();
        if (pid.isEmpty()) {
            OfflineServer.setStatus(404);
            return out;
        }
        deleteExpired();
        if (pid.equals(Slots.current())) {
            // the current player's files may be behind its in-memory copies
            ProfileStore.save();
            ServerState.save();
        }
        String code;
        File d;
        do {
            code = String.format(java.util.Locale.US, "%06d", RANDOM.nextInt(1000000));
            d = new File(dir(), code);
        } while (d.exists());
        d.mkdirs();
        for (String base : FILES) {
            File src = Slots.fileFor(base, pid);
            if (src.exists()) {
                Slots.writeJson(new File(d, base), Slots.read(src));
            }
        }
        JSONObject info = new JSONObject();
        info.put("pid", pid);
        info.put("created", System.currentTimeMillis());
        Slots.writeJson(new File(d, "code.json"), info);
        Log.i(TAG, "save code " + code + " = copy of " + pid);

        out.put("slot", slot == Slots.NO_SLOT ? Math.max(0, Slots.indexOf(pid)) : slot);
        out.put("profileId", pid);
        out.put("code", code);
        out.put("ttl", TTL);
        return out;
    }

    private static void deleteExpired() {
        File[] codes = dir().listFiles();
        if (codes == null) {
            return;
        }
        for (File d : codes) {
            long created = Slots.read(new File(d, "code.json")).optLong("created", 0);
            if (System.currentTimeMillis() - created > TTL * 1000L) {
                File[] files = d.listFiles();
                if (files != null) {
                    for (File f : files) {
                        f.delete();
                    }
                }
                d.delete();
                Log.i(TAG, "save code " + d.getName() + " expired");
            }
        }
    }

    /** PUT v1/userprofile/slot: a new player in the slot, copied from the code's snapshot. */
    static synchronized JSONObject linkSlot(JSONObject in) throws JSONException {
        String code = in.optString("code", "").trim().replaceAll("[^0-9]", "");
        long slot = in.optLong("slot", Slots.NO_SLOT);
        File d = new File(dir(), code);
        JSONObject out = new JSONObject();
        long created = Slots.read(new File(d, "code.json")).optLong("created", 0);
        if (code.isEmpty() || !new File(d, "profile.json").exists() || slot < 0 || slot >= Slots.COUNT
                || System.currentTimeMillis() - created > TTL * 1000L) {
            Log.i(TAG, "save code " + code + ": unknown (slot " + slot + ")");
            OfflineServer.setStatus(404);
            return out;
        }
        String pid = Slots.newPid();
        for (String base : FILES) {
            File src = new File(d, base);
            if (!src.exists()) {
                continue;
            }
            JSONObject o = Slots.read(src);
            if (base.equals("profile.json")) {
                o.put("pid", pid);
            }
            Slots.writeJson(Slots.fileFor(base, pid), o);
        }
        String old = Slots.pidAt((int) slot);
        Slots.assign((int) slot, pid);
        Log.i(TAG, "save code " + code + " -> slot " + slot + " (" + pid + ")"
                + (old.isEmpty() ? "" : ", replaces " + old + " (its files are kept)"));
        return out;
    }
}
