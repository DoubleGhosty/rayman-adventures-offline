package com.rayman.offline;

import android.util.Log;

import org.json.JSONArray;
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
 * The three save slots of the title screen "Sauvegardes" menu (files/rlc/slots.json).
 *
 * Ubisoft's server kept one player profile per slot, each with its own save. The device only holds
 * the game being played; choosing a slot in the menu sends userprofile/session {slot} and the answer
 * decides (userProfileModule::onGameServerRequestDone, StartSession):
 *   - empty slot          -> a new pid + forceNewGame: the game starts from zero;
 *   - slot of another pid -> that pid + its last uploaded "save" (base64): the game loads it;
 *   - slot of the current -> same pid, empty save: the local game goes on.
 * Every player has its own server files: the first one (slot A of existing installs) keeps the
 * historical names (profile.json, state.json, ghost.json), the others get a suffix (profile_0002.json).
 */
final class Slots {

    private static final String TAG = OfflineServer.TAG;
    private static final Charset UTF8 = Charset.forName("UTF-8");

    static final int COUNT = 3;
    static final long NO_SLOT = 4294967295L;
    private static final String PREFIX = "offline-player-";

    private static JSONObject data;

    private Slots() {
    }

    private static File file() {
        return new File(OfflineServer.dataDir, "slots.json");
    }

    private static synchronized JSONObject data() {
        if (data == null) {
            data = read(file());
            try {
                if (!data.has("slots")) {
                    // first run of this version: the existing profile becomes slot A
                    JSONArray s = new JSONArray();
                    String main = readPid(new File(OfflineServer.dataDir, "profile.json"));
                    s.put(main.isEmpty() ? RlcApi.PLAYER_PID : main);
                    for (int i = 1; i < COUNT; i++) {
                        s.put("");
                    }
                    data.put("slots", s);
                    data.put("main", s.getString(0));
                    data.put("current", s.getString(0));
                    data.put("next", 2);
                    save();
                }
            } catch (JSONException e) {
                Log.e(TAG, "slots init", e);
            }
        }
        return data;
    }

    static synchronized String current() {
        return data().optString("current", RlcApi.PLAYER_PID);
    }

    static synchronized String pidAt(int slot) {
        JSONArray s = data().optJSONArray("slots");
        return s == null || slot < 0 || slot >= s.length() ? "" : s.optString(slot, "");
    }

    static synchronized int indexOf(String pid) {
        for (int i = 0; i < COUNT; i++) {
            if (pidAt(i).equals(pid)) {
                return i;
            }
        }
        return -1;
    }

    static synchronized void assign(int slot, String pid) throws JSONException {
        data().getJSONArray("slots").put(slot, pid);
        save();
    }

    /** Makes pid the player the server works for (profile, incubator, daily state...). */
    static synchronized void setCurrent(String pid) throws JSONException {
        if (!pid.equals(current())) {
            Log.i(TAG, "slots: current player " + current() + " -> " + pid);
            data().put("current", pid);
            save();
            ProfileStore.reset();
            ServerState.reset();
        }
        if (indexOf(pid) < 0) {
            // a pid the server did not know (older install): first free slot
            for (int i = 0; i < COUNT; i++) {
                if (pidAt(i).isEmpty()) {
                    assign(i, pid);
                    break;
                }
            }
        }
    }

    static synchronized String newPid() throws JSONException {
        int n = data().optInt("next", 2);
        String pid;
        do {
            pid = PREFIX + String.format(java.util.Locale.US, "%04d", n++);
        } while (indexOf(pid) >= 0 || new File(OfflineServer.dataDir, fileName("profile.json", pid)).exists());
        data().put("next", n);
        save();
        return pid;
    }

    /** Server file of a player: the first player keeps the historical name. */
    static String fileName(String base, String pid) {
        String main = mainPid();
        if (pid.isEmpty() || pid.equals(main)) {
            return base;
        }
        String id = pid.startsWith(PREFIX) ? pid.substring(PREFIX.length()) : pid;
        id = id.replaceAll("[^A-Za-z0-9-]", "_");
        int dot = base.lastIndexOf('.');
        return base.substring(0, dot) + "_" + id + base.substring(dot);
    }

    static File fileFor(String base) {
        return new File(OfflineServer.dataDir, fileName(base, current()));
    }

    static File fileFor(String base, String pid) {
        return new File(OfflineServer.dataDir, fileName(base, pid));
    }

    /** pid owning the historical file names. */
    static synchronized String mainPid() {
        JSONObject d = data;
        if (d == null) {
            d = data();
        }
        if (!d.has("main")) {
            try {
                String main = readPid(new File(OfflineServer.dataDir, "profile.json"));
                d.put("main", main.isEmpty() ? RlcApi.PLAYER_PID : main);
                save();
            } catch (JSONException ignored) {
            }
        }
        return d.optString("main", RlcApi.PLAYER_PID);
    }

    static synchronized JSONObject dump() {
        return data();
    }

    private static String readPid(File f) {
        return read(f).optString("pid", "");
    }

    private static synchronized void save() {
        File f = file();
        File tmp = new File(f.getPath() + ".tmp");
        try {
            FileOutputStream out = new FileOutputStream(tmp);
            try {
                out.write(data.toString().getBytes(UTF8));
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

    static void writeJson(File f, JSONObject o) {
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

    static JSONObject read(File f) {
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
}
