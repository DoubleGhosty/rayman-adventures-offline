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
import java.util.Calendar;
import java.util.TimeZone;

/**
 * State that only the server owned (daily reward claims, challenge scores...), persisted in
 * files/rlc/state.json. Unlike profile.json it is never replaced by a client upload.
 */
final class ServerState {

    private static final String TAG = OfflineServer.TAG;
    private static final Charset UTF8 = Charset.forName("UTF-8");

    private static JSONObject state;

    private ServerState() {
    }

    private static File file() {
        return Slots.fileFor("state.json");      // one per save slot player
    }

    /** Current player changed (Slots.setCurrent). */
    static synchronized void reset() {
        state = null;
    }

    static synchronized JSONObject get() {
        if (state == null) {
            state = read(file());
        }
        return state;
    }

    /** Sub-object of the state, created on first use. */
    static synchronized JSONObject section(String name) {
        JSONObject o = get().optJSONObject(name);
        if (o == null) {
            o = new JSONObject();
            try {
                get().put(name, o);
            } catch (JSONException ignored) {
            }
        }
        return o;
    }

    static synchronized void save() {
        File f = file();
        File tmp = new File(f.getPath() + ".tmp");
        try {
            FileOutputStream out = new FileOutputStream(tmp);
            try {
                out.write(get().toString().getBytes(UTF8));
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

    /** Day number in the device's time zone (days are what daily rewards and challenges rotate on). */
    static long today() {
        return dayOf(System.currentTimeMillis());
    }

    static long dayOf(long millis) {
        long offset = TimeZone.getDefault().getOffset(millis);
        return Math.floorDiv(millis + offset, 86400000L);
    }

    /** Milliseconds (UTC) at which the given local day starts. */
    static long dayStart(long day) {
        long approx = day * 86400000L;
        return approx - TimeZone.getDefault().getOffset(approx);
    }

    /** Seconds until the next local midnight. */
    static long secondsToNextDay() {
        Calendar c = Calendar.getInstance();
        long now = c.getTimeInMillis();
        c.add(Calendar.DAY_OF_MONTH, 1);
        c.set(Calendar.HOUR_OF_DAY, 0);
        c.set(Calendar.MINUTE, 0);
        c.set(Calendar.SECOND, 0);
        c.set(Calendar.MILLISECOND, 0);
        return Math.max(1, (c.getTimeInMillis() - now) / 1000);
    }

    private static JSONObject read(File f) {
        if (!f.exists()) {
            return new JSONObject();
        }
        try {
            InputStream in = new FileInputStream(f);
            try {
                ByteArrayOutputStream out = new ByteArrayOutputStream();
                byte[] buf = new byte[8192];
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
