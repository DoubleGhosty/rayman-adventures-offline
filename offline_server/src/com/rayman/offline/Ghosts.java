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
 * Challenge ghosts ("v1/ghosts/*", online::rlcGhostsModule, handled by ITF::GhostManager).
 *
 *   uploadGhost {data: base64 ghost file} -> GameServerEmpty
 *   getGhost    -> online::rlcGhostData {data: base64 ghost file}
 *
 * The real server picked another player's ghost to race against. Offline the rival is the player's
 * own last uploaded run. GhostManager::onGetOnlineGhostSuccess checks the ghost header against the
 * current challenge and, when it belongs to another day, falls back to onGetOnlineGhostFail, which
 * starts the run without a ghost. When no ghost was ever uploaded the request fails (HTTP 404) so the
 * client takes that same path: an empty "data" would make it stop without starting the run.
 */
final class Ghosts {

    private static final String TAG = OfflineServer.TAG;
    private static final Charset UTF8 = Charset.forName("UTF-8");

    private Ghosts() {
    }

    private static File file() {
        return Slots.fileFor("ghost.json");      // one per save slot player
    }

    static synchronized void upload(JSONObject in) {
        String data = in.optString("data", "");
        if (data.isEmpty()) {
            return;
        }
        try {
            JSONObject o = new JSONObject();
            o.put("data", data);
            o.put("day", ServerState.today());
            FileOutputStream out = new FileOutputStream(file());
            try {
                out.write(o.toString().getBytes(UTF8));
            } finally {
                out.close();
            }
            Log.i(TAG, "ghost: stored (" + data.length() + " base64 chars)");
        } catch (IOException | JSONException e) {
            Log.e(TAG, "ghost: cannot store", e);
        }
    }

    static synchronized JSONObject get() throws JSONException {
        File f = file();
        if (f.exists()) {
            try {
                InputStream in = new FileInputStream(f);
                try {
                    ByteArrayOutputStream out = new ByteArrayOutputStream();
                    byte[] buf = new byte[16384];
                    int r;
                    while ((r = in.read(buf)) > 0) {
                        out.write(buf, 0, r);
                    }
                    JSONObject o = new JSONObject(new String(out.toByteArray(), UTF8));
                    JSONObject ans = new JSONObject();
                    ans.put("data", o.optString("data", ""));
                    return ans;
                } finally {
                    in.close();
                }
            } catch (IOException e) {
                Log.e(TAG, "ghost: cannot read", e);
            }
        }
        OfflineServer.setStatus(404);
        return new JSONObject();
    }
}
