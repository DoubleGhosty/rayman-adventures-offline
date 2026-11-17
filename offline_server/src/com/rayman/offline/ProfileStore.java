package com.rayman.offline;

import android.util.Log;

import org.json.JSONException;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.Charset;

/**
 * Server-side player profile, persisted in files/rlc/profile.json.
 *
 * The real game server was authoritative for the creature list and the incubator, but the client
 * uploads its whole profile (POST v1/userprofile/save, same ITF JSON format as the answers) before
 * it asks for them. We keep the last upload and serve state back from it, so the local progress is
 * never overwritten by empty answers. Server-side game logic (incubation, hatching, rewards) edits
 * this profile; the client then saves it back on its next upload.
 */
final class ProfileStore {

    private static final String TAG = OfflineServer.TAG;
    private static final Charset UTF8 = Charset.forName("UTF-8");

    private static JSONObject profile;

    private ProfileStore() {
    }

    private static File file(String name) {
        return new File(OfflineServer.dataDir, name);
    }

    static synchronized JSONObject get() {
        if (profile == null) {
            profile = read(Slots.fileFor("profile.json"));
        }
        return profile;
    }

    /** Current player changed (Slots.setCurrent): reload from that player's file. */
    static synchronized void reset() {
        profile = null;
    }

    /** Stores the save (base64 universe) of a player, e.g. the game being left in the slot menu. */
    static synchronized void storeSave(String pid, String save) {
        JSONObject p = of(pid);
        try {
            p.put("save", save);
            if (!p.has("pid")) {
                p.put("pid", pid);
            }
        } catch (JSONException ignored) {
        }
        if (pid.equals(Slots.current())) {
            profile = p;
        }
        write(Slots.fileFor("profile.json", pid), p);
    }

    /** Stored profile of any player (save slots), without making it current. */
    static synchronized JSONObject of(String pid) {
        if (pid.equals(Slots.current())) {
            return get();
        }
        return read(Slots.fileFor("profile.json", pid));
    }

    static synchronized boolean hasProfile() {
        return get().length() > 0;
    }

    /** Replaces the profile with a client upload (keeps a copy of the very first one). */
    static synchronized void putUpload(JSONObject upload) {
        if (!file("profile_initial.json").exists()) {
            write(file("profile_initial.json"), upload);
        }
        String pid = upload.optString("pid", "");
        if (!pid.isEmpty() && !pid.equals(Slots.current())) {
            // upload of another slot's player (should not happen): kept in its own file
            JSONObject other = of(pid);
            JSONObject inc = other.optJSONObject("incubationData");
            try {
                if (inc != null) {
                    upload.put("incubationData", inc);
                }
            } catch (JSONException ignored) {
            }
            write(Slots.fileFor("profile.json", pid), upload);
            return;
        }
        // the incubator is server-authoritative: the client only echoes what we told it
        JSONObject inc = get().optJSONObject("incubationData");
        if (inc != null) {
            try {
                upload.put("incubationData", inc);
            } catch (JSONException ignored) {
            }
        }
        profile = upload;
        save();
    }

    static synchronized void save() {
        write(Slots.fileFor("profile.json"), get());
    }

    /** Current incubation block (online::incubationStatusResult format). */
    static synchronized JSONObject incubation() {
        JSONObject inc = get().optJSONObject("incubationData");
        if (inc == null) {
            inc = emptyIncubation();
            try {
                get().put("incubationData", inc);
            } catch (JSONException ignored) {
            }
        }
        return inc;
    }

    static JSONObject emptyIncubation() {
        try {
            JSONObject reward = new JSONObject();
            reward.put("type", 0);
            reward.put("creatureID", 4294967295L);
            reward.put("count", 0);
            reward.put("elixirType0", 0);
            reward.put("elixirType1", 0);
            reward.put("elixirType2", 0);
            reward.put("ticketType", 3);
            reward.put("jackpot", false);
            reward.put("seasonalFixedReward", false);
            JSONObject inc = new JSONObject();
            inc.put("hatchingEnd", "0000-00-00T00:00:00+00:00");
            inc.put("timeLeft", 0);
            inc.put("creatureId", 4294967295L);
            inc.put("eggAdventureSequence", 0);
            inc.put("eggAdventureRegion", 0);
            inc.put("autoHatch", false);
            inc.put("decoyRewardType", 0);
            inc.put("decoyReward", reward);
            return inc;
        } catch (JSONException e) {
            return new JSONObject();
        }
    }

    private static JSONObject read(File f) {
        if (!f.exists()) {
            return new JSONObject();
        }
        try {
            InputStream in = new FileInputStream(f);
            try {
                ByteArrayOutputStream out = new ByteArrayOutputStream();
                byte[] buf = new byte[16384];
                int r;
                while ((r = in.read(buf)) > 0) {
                    out.write(buf, 0, r);
                }
                return new JSONObject(new String(out.toByteArray(), UTF8));
            } finally {
                in.close();
            }
        } catch (IOException | JSONException e) {
            Log.e(TAG, "cannot read " + f, e);
            return new JSONObject();
        }
    }

    private static void write(File f, JSONObject o) {
        File tmp = new File(f.getPath() + ".tmp");
        try {
            FileOutputStream out = new FileOutputStream(tmp);
            try {
                out.write(o.toString().getBytes(UTF8));
            } finally {
                out.close();
            }
            if (!tmp.renameTo(f)) {
                Log.e(TAG, "cannot replace " + f);
            }
        } catch (IOException e) {
            Log.e(TAG, "cannot write " + f, e);
        }
    }
}
