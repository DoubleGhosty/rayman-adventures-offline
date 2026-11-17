package com.rayman.offline;

import android.content.Context;
import android.util.Log;

import java.io.BufferedInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.Charset;
import java.security.KeyStore;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;
import java.util.TimeZone;

import javax.net.ssl.KeyManagerFactory;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLServerSocket;

/**
 * Embedded replacement for the Ubisoft online services (port of mock_server.py).
 *
 * libuaf.so is patched so that every "*.ubi.com" host resolves to 127.0.0.1 and
 * connections to 127.0.0.1:80 / :443 are redirected to the ports below.
 * TLS certificate checks are already bypassed inside libuaf.so, so a self-signed
 * certificate (assets/offline/server.p12) is enough for the HTTPS side.
 */
public final class OfflineServer {

    static final String TAG = "RaymanOffline";
    static final int HTTP_PORT = 18080;
    static final int HTTPS_PORT = 18443;
    static final String BASE = "http://127.0.0.1:" + HTTP_PORT;
    private static final Charset UTF8 = Charset.forName("UTF-8");
    private static final String KEYSTORE_ASSET = "offline/server.p12";
    private static final char[] KEYSTORE_PASS = "android".toCharArray();

    static final String PROFILE_ID = "5b1e6a0c-8d3f-4c2a-9e71-0a4f2b6c8d10";
    static final String SESSION_ID = "c4f7d2e1-6b9a-4e3c-8f15-2d7a9b0e4c61";

    /** App-private directory for the emulated server state (files/rlc/). */
    static java.io.File dataDir;

    private static boolean started;
    private static byte[] storeData;

    private OfflineServer() {
    }

    public static synchronized void start(Context ctx) {
        if (started) {
            return;
        }
        started = true;
        final Context app = ctx.getApplicationContext() != null ? ctx.getApplicationContext() : ctx;
        dataDir = new java.io.File(app.getFilesDir(), "rlc");
        dataDir.mkdirs();
        try {
            storeData = readAsset(app, "offline/store_v2.json");
        } catch (IOException e) {
            Log.e(TAG, "store_v2.json asset missing", e);
            storeData = "{}".getBytes(UTF8);
        }
        try {
            Rewards.load(new String(readAsset(app, "offline/ticket_weights.json"), UTF8));
        } catch (IOException e) {
            Log.e(TAG, "ticket_weights.json asset missing", e);
        }
        // 127.0.0.1: native curl traffic (getaddrinfo/connect hooks)
        // ::1      : game server base URL patched to http://[::1]:18080 (Java NetworkController)
        for (String addr : new String[]{"127.0.0.1", "::1"}) {
            try {
                ServerSocket http = new ServerSocket(HTTP_PORT, 50, InetAddress.getByName(addr));
                spawnAcceptLoop(http, "http");
            } catch (IOException e) {
                Log.e(TAG, "Cannot bind HTTP " + addr + ":" + HTTP_PORT, e);
            }
        }
        try {
            KeyStore ks = KeyStore.getInstance("PKCS12");
            InputStream in = app.getAssets().open(KEYSTORE_ASSET);
            try {
                ks.load(in, KEYSTORE_PASS);
            } finally {
                in.close();
            }
            KeyManagerFactory kmf = KeyManagerFactory.getInstance(KeyManagerFactory.getDefaultAlgorithm());
            kmf.init(ks, KEYSTORE_PASS);
            SSLContext ssl = SSLContext.getInstance("TLS");
            ssl.init(kmf.getKeyManagers(), null, null);
            SSLServerSocket https = (SSLServerSocket) ssl.getServerSocketFactory()
                    .createServerSocket(HTTPS_PORT, 50, InetAddress.getByName("127.0.0.1"));
            spawnAcceptLoop(https, "https");
        } catch (Exception e) {
            Log.e(TAG, "Cannot start HTTPS server on port " + HTTPS_PORT, e);
        }
        Log.i(TAG, "Offline services ready on 127.0.0.1:" + HTTP_PORT + " / :" + HTTPS_PORT);
    }

    private static void spawnAcceptLoop(ServerSocket server, String name) {
        Thread t = new Thread(new AcceptLoop(server, name), "RaymanOffline-" + name);
        t.setDaemon(true);
        t.start();
    }

    // Named classes on purpose: d8 (build-tools 34) crashes on nested anonymous classes.
    static final class AcceptLoop implements Runnable {
        private final ServerSocket server;
        private final String name;

        AcceptLoop(ServerSocket server, String name) {
            this.server = server;
            this.name = name;
        }

        @Override
        public void run() {
            while (true) {
                try {
                    Socket s = server.accept();
                    Thread worker = new Thread(new Connection(s, name), "RaymanOffline-" + name + "-conn");
                    worker.setDaemon(true);
                    worker.start();
                } catch (IOException e) {
                    Log.e(TAG, name + " accept failed", e);
                    try {
                        Thread.sleep(200);
                    } catch (InterruptedException ignored) {
                        return;
                    }
                }
            }
        }
    }

    static final class Connection implements Runnable {
        private final Socket socket;
        private final String scheme;

        Connection(Socket socket, String scheme) {
            this.socket = socket;
            this.scheme = scheme;
        }

        @Override
        public void run() {
            handleConnection(socket, scheme);
        }
    }

    // ---------------------------------------------------------------- HTTP/1.1

    private static void handleConnection(Socket s, String scheme) {
        int served = 0;
        Log.d(TAG, "accept " + scheme + " from :" + s.getPort());
        try {
            s.setSoTimeout(30000);
            InputStream in = new BufferedInputStream(s.getInputStream());
            OutputStream out = s.getOutputStream();
            while (true) {
                String requestLine = readLine(in);
                if (requestLine == null) {
                    break;
                }
                if (requestLine.length() == 0) {
                    continue;
                }
                String[] parts = requestLine.split(" ");
                if (parts.length < 2) {
                    break;
                }
                String method = parts[0];
                String path = parts[1];
                String host = "";
                int contentLength = 0;
                boolean chunked = false;
                boolean close = parts.length > 2 && parts[2].equals("HTTP/1.0");
                boolean expectContinue = false;
                String line;
                while ((line = readLine(in)) != null && line.length() > 0) {
                    int c = line.indexOf(':');
                    if (c <= 0) {
                        continue;
                    }
                    String k = line.substring(0, c).trim().toLowerCase(Locale.US);
                    String v = line.substring(c + 1).trim();
                    if (k.equals("host")) {
                        host = v;
                    } else if (k.equals("content-length")) {
                        try {
                            contentLength = Integer.parseInt(v);
                        } catch (NumberFormatException ignored) {
                        }
                    } else if (k.equals("transfer-encoding") && v.toLowerCase(Locale.US).contains("chunked")) {
                        chunked = true;
                    } else if (k.equals("connection") && v.equalsIgnoreCase("close")) {
                        close = true;
                    } else if (k.equals("expect") && v.equalsIgnoreCase("100-continue")) {
                        expectContinue = true;
                    }
                }
                if (line == null) {
                    break;
                }
                if (expectContinue) {
                    out.write("HTTP/1.1 100 Continue\r\n\r\n".getBytes(UTF8));
                    out.flush();
                }
                byte[] body = chunked ? readChunked(in) : readFully(in, contentLength);

                STATUS.set(200);
                CONTENT_TYPE.set("application/json");
                byte[] resp = route(method, path, body);
                int status = STATUS.get();
                served++;
                Log.i(TAG, "[" + scheme + "://" + host + "] " + method + " " + path
                        + " (" + body.length + "B in) -> " + status + " (" + (resp == null ? 0 : resp.length) + "B)");
                if (body.length > 0) {
                    Log.d(TAG, "  body: " + new String(body, 0, Math.min(body.length, 2000), UTF8));
                }

                StringBuilder h = new StringBuilder();
                h.append("HTTP/1.1 ").append(status).append(status == 200 ? " OK" : " Error").append("\r\n");
                h.append("Content-Type: ").append(CONTENT_TYPE.get()).append("\r\n");
                h.append("Access-Control-Allow-Origin: *\r\n");
                // game server answers: signature (verification patched out in libuaf) + server clock
                h.append("rlc-hash: offline\r\n");
                h.append("rlc-time: ").append(isoNow()).append("\r\n");
                // MobileAuth network clock (libuaf _ubimobile_networkTime_thread): GET
                // http://gamecfg-mob.ubi.com/profile/?epoch=1, reads atof() after "Server-Time:" in the
                // headers of a 200 answer. Without it a new install cannot create its Ubisoft account
                // ("MobileAuth_GetExisting -14 unable get network time"): no UbiServices session, no game
                // server, and every server action (incubator...) fails once the tutorial is over.
                h.append("Server-Time: ").append(String.format(Locale.US, "%.3f", System.currentTimeMillis() / 1000.0))
                        .append("\r\n");
                h.append("Content-Length: ").append(resp == null ? 0 : resp.length).append("\r\n");
                h.append(close ? "Connection: close\r\n" : "Connection: keep-alive\r\n");
                h.append("\r\n");
                out.write(h.toString().getBytes(UTF8));
                if (resp != null && !method.equals("HEAD")) {
                    out.write(resp);
                }
                out.flush();
                if (close) {
                    break;
                }
            }
        } catch (IOException e) {
            // keep-alive timeout / client close after a response is normal; anything else is worth logging
            if (served == 0) {
                Log.w(TAG, scheme + " connection failed before any request: " + e);
            }
        } finally {
            try {
                s.close();
            } catch (IOException ignored) {
            }
        }
    }

    // ---------------------------------------------------------------- routes

    /** HTTP status of the response being built on this connection thread (200 unless a route says otherwise). */
    private static final ThreadLocal<Integer> STATUS = new ThreadLocal<Integer>();

    /** Content-Type of the response being built on this connection thread (JSON unless a route says otherwise). */
    private static final ThreadLocal<String> CONTENT_TYPE = new ThreadLocal<String>();

    static void setStatus(int status) {
        STATUS.set(status);
    }

    static byte[] route(String method, String path, byte[] body) {
        if (method.equals("HEAD")) {
            return new byte[0];
        }
        if (path.startsWith("/offline/admin/")) {
            return Admin.route(method, path, body);
        }
        if (RlcApi.handles(path)) {
            return RlcApi.route(method, path, body);
        }
        if (method.equals("GET")) {
            if (path.startsWith("/v1/news/")) {
                CONTENT_TYPE.set("text/html; charset=utf-8");
                return newsPage(path.substring("/v1/news/".length()));
            }
            if (path.startsWith("/v1/applications/") && path.contains("/configuration")) {
                // ubiservices::ConfigInfo binding table (libuaf 0x24dd100)
                return json("{\"platformConfig\":{},\"resources\":[],\"legacyUrls\":[],\"sandboxes\":[],"
                        + "\"uplayServices\":[],\"punch\":{},\"sdkConfig\":{},\"featuresSwitches\":" + featureSwitches() + ","
                        + "\"gatewayResources\":[],\"custom\":{}}");
            }
            if (path.contains("/store")) {
                return storeData;
            }
            if (path.contains("product=708") || path.startsWith("/?")) {
                return houstonConfig();
            }
            if (path.contains("entities")) {
                return json("{\"entities\":[]}");
            }
            return genericOk();
        }
        if (method.equals("POST")) {
            if (path.contains("/profiles/sessions")) {
                return session();
            }
            if (path.contains("register_device") || path.contains("profile")) {
                return json("{\"device\":{\"federated_id\":\"kL0R7Od1toC3MljqCGepVM1ET77yOd6dY656Vi7pHKym5SNIy17uO98Hhfg5sWir\","
                        + "\"ubimobi_access_token\":\"YZLnU3wSjysqDwCL5o96BLJu1bvqh9Zg9LD3RaWbJFBmDe70Dh7e3RJ52fvkouBy\"}}");
            }
            if (path.contains("sessions")) {
                return session();
            }
            if (path.contains("entities")) {
                return json("{\"entities\":[]}");
            }
            return genericOk();
        }
        // PUT, DELETE, ...
        return genericOk();
    }

    /**
     * Title screen "Actualites": the game's WebView opens http://127.0.0.1:18080/v1/news/<language>
     * (libuaf patch of GameServerModule::getNewsURL). Ubisoft's news pages are gone: a short page says so.
     * Language = ITF language index (1 = French).
     */
    private static byte[] newsPage(String lang) {
        boolean fr = lang.startsWith("1");
        String title = fr ? "Pas d'actualité" : "No news";
        String text = fr
                ? "Les serveurs d'Ubisoft sont fermés : cette version de Rayman Adventures fonctionne hors ligne."
                + " Les actualités ne sont plus publiées."
                : "Ubisoft's servers are closed: this version of Rayman Adventures runs offline."
                + " News are no longer published.";
        return json("<!doctype html><html><head><meta charset=\"utf-8\">"
                + "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
                + "<style>html,body{height:100%;margin:0}body{display:flex;align-items:center;justify-content:center;"
                + "background:#0b3d5c;color:#fff;font-family:sans-serif;text-align:center}"
                + "div{max-width:32em;padding:1.5em}h1{font-size:1.6em;margin:0 0 .6em}p{font-size:1.1em;line-height:1.4}"
                + "</style></head><body><div><h1>" + title + "</h1><p>" + text + "</p></div></body></html>");
    }

    private static byte[] houstonConfig() {
        String b = BASE;
        return json("{"
                + "\"ads_config\":\"" + b + "/ads/\","
                + "\"amazon_receipt_validation\":\"" + b + "/partners/amazon/\","
                + "\"apple_receipt_validation\":\"" + b + "/partners/apple/\","
                + "\"crosspromo_server_url\":\"" + b + "\","
                + "\"dlc_check\":\"" + b + "/check_dlc.php\","
                + "\"dynamic_download\":\"" + b + "/\","
                + "\"flurry_reward_check\":\"" + b + "/partners/flurry/\","
                + "\"game_session\":\"" + b + "/gamesession/\","
                + "\"google_receipt_validation\":\"" + b + "/partners/google/\","
                + "\"houston_api\":\"" + b + "/api/\","
                + "\"houston_leaderboard\":\"" + b + "/leaderboard/\","
                + "\"inapp_receipt_validation\":\"" + b + "/partners/\","
                + "\"ingame_dynamic_store\":\"" + b + "/store/\","
                + "\"ingame_dynamic_store_refresh_rat\":\"15\","
                + "\"microsoft_receipt_validation\":\"" + b + "/partners/windows/\","
                + "\"msdk_ingame_dynamic_store\":\"" + b + "/store/v2/\","
                + "\"tapjoy_reward_check\":\"" + b + "/partners/tapjoy/\","
                + "\"trialpay_reward_check\":\"" + b + "/partners/trialpay/\","
                + "\"user_profile\":\"" + b + "/profile/\","
                + "\"use_magnet_1_0\":\"yes\","
                + "\"use_magnet_2_0\":\"no\","
                + "\"use_cp2\":\"1\","
                + "\"environment\":\"production\""
                + "}");
    }

    /**
     * ubiservices::FeatureSwitchId names (libuaf FeatureSwitchId::getString). Services that make no sense
     * offline are switched off: the SDK then completes those jobs immediately ("feature/service shut down by
     * feature switch") instead of waiting forever. EntitiesSpace off => the "nodeConfig" lookup of
     * GameServerModule fails fast and the game falls back to its (patched) default game-server URL.
     */
    private static final String[] DISABLED_FEATURES = {
            "ApplicationUsed", "Connection", "ContentFiltering", "EntitiesSpace", "Event", "FixAccountIssues",
            "FriendsLookup", "FriendsRequest", "Messaging", "News", "Populations", "ProfilesExternal",
            "SendPopulationsInPlayerStart", "SendPrimaryStoreEvent", "Socialfeed", "UplayFriends", "UplayLaunch",
            "UplayWinActions", "UplayWinRewards", "UsersManagement", "WebSocketClient"};

    private static String featureSwitches() {
        StringBuilder sb = new StringBuilder("[");
        for (int i = 0; i < DISABLED_FEATURES.length; i++) {
            if (i > 0) {
                sb.append(',');
            }
            sb.append("{\"name\":\"").append(DISABLED_FEATURES[i]).append("\",\"value\":false}");
        }
        return sb.append(']').toString();
    }

    private static byte[] session() {
        SimpleDateFormat fmt = new SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss.SSS'0000Z'", Locale.US);
        fmt.setTimeZone(TimeZone.getTimeZone("UTC"));
        Date now = new Date();
        Date exp = new Date(now.getTime() + 365L * 24 * 3600 * 1000);
        // ubiservices::SessionInfo::parseJson requires (presence mask 0xeff): ticket, profileId (GUID),
        // hasAcceptedLegalOptins (bool), spaceId, environment, expiration, serverTime, clientIp,
        // sessionId (GUID), platformType, accountIssues (array).
        return json("{\"platformType\":\"uplay\",\"environment\":\"Prod\",\"ticket\":\"v1.offline_ticket_rayman\","
                + "\"expiration\":\"" + fmt.format(exp) + "\",\"clientIpCountry\":\"FR\",\"rememberMeTicket\":null,"
                + "\"twoFactorAuthenticationTicket\":null,"
                + "\"hasAcceptedLegalOptins\":true,\"accountIssues\":[],"
                + "\"profileId\":\"" + PROFILE_ID + "\","
                + "\"userId\":\"" + PROFILE_ID + "\","
                + "\"nameOnPlatform\":\"RaymanPlayer\",\"sessionKey\":\"offline_session_key\","
                + "\"spaceId\":\"e0b7ffaa-09a0-423e-b0a7-822f485b24ed\",\"clientIp\":\"127.0.0.1\","
                + "\"serverTime\":\"" + fmt.format(now) + "\","
                + "\"sessionId\":\"" + SESSION_ID + "\"}");
    }

    static String isoNow() {
        SimpleDateFormat fmt = new SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss.SSS'Z'", Locale.US);
        fmt.setTimeZone(TimeZone.getTimeZone("UTC"));
        return fmt.format(new Date());
    }

    private static byte[] genericOk() {
        return json("{\"status\":200,\"result\":\"ok\"}");
    }

    private static byte[] json(String s) {
        return s.getBytes(UTF8);
    }

    // ---------------------------------------------------------------- io helpers

    private static String readLine(InputStream in) throws IOException {
        ByteArrayOutputStream buf = new ByteArrayOutputStream(128);
        int c;
        while ((c = in.read()) != -1) {
            if (c == '\n') {
                break;
            }
            if (c != '\r') {
                buf.write(c);
            }
            if (buf.size() > 65536) {
                throw new IOException("header line too long");
            }
        }
        if (c == -1 && buf.size() == 0) {
            return null;
        }
        return new String(buf.toByteArray(), UTF8);
    }

    private static byte[] readFully(InputStream in, int n) throws IOException {
        byte[] b = new byte[Math.max(0, n)];
        int off = 0;
        while (off < b.length) {
            int r = in.read(b, off, b.length - off);
            if (r < 0) {
                throw new IOException("truncated body");
            }
            off += r;
        }
        return b;
    }

    private static byte[] readChunked(InputStream in) throws IOException {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        while (true) {
            String sizeLine = readLine(in);
            if (sizeLine == null) {
                throw new IOException("truncated chunk");
            }
            int semi = sizeLine.indexOf(';');
            int size = Integer.parseInt((semi >= 0 ? sizeLine.substring(0, semi) : sizeLine).trim(), 16);
            if (size == 0) {
                String l;
                while ((l = readLine(in)) != null && l.length() > 0) {
                    // trailers
                }
                return out.toByteArray();
            }
            out.write(readFully(in, size));
            readLine(in);
        }
    }

    private static byte[] readAsset(Context ctx, String name) throws IOException {
        InputStream in = ctx.getAssets().open(name);
        try {
            ByteArrayOutputStream out = new ByteArrayOutputStream();
            byte[] buf = new byte[16384];
            int r;
            while ((r = in.read(buf)) > 0) {
                out.write(buf, 0, r);
            }
            return out.toByteArray();
        } finally {
            in.close();
        }
    }
}
