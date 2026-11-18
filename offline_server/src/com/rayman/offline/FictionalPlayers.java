package com.rayman.offline;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

/**
 * Fictional players of the leaderboards (the tree ranking, the adventure maps, the daily challenge),
 * so that the player is no longer alone in them.
 *
 * Everything is derived from a hash of the player's index (and of the day, for the challenge): the same
 * players come back with the same names, countries and costumes, nothing is stored. Their ids start with
 * "npc-" (Leaderboards.shortProfiles / userProfile answer for them).
 *
 * Their score in the tree ranking is the stars of their Incrediballs (RLC_CreatureManager::
 * getStarsTotalNb: 1 per common, 2 per uncommon, 3 per rare, 4 per queen - read from the game's
 * RLC_CreatureManager_Template - so 894 at most; the tree is 10 m per star + 70 m), and their profile
 * holds Incrediballs worth those stars (asset offline/creatures.json), so their card and their tree
 * ("Visiter") match their height.
 *
 * Names: half of them have the game's default name, the one the client gave the player ("AVENTURIER
 * 614438": the word comes from the player's own default name, so it is in the player's language), the
 * others a nickname. A quarter of them are from the player's country (the "Pays" filter).
 */
final class FictionalPlayers {

    static final String PID_PREFIX = "npc-";
    /** Players of the tree ranking (and of each map ranking). */
    static final int WORLD = 600;
    /** Players of each day's challenge. */
    static final int CHALLENGE = 400;
    private static final int MAX_STARS = 894;           // 101 commons, 104 uncommons, 115 rares, 60 queens
    /** Stars of an Incrediball of each rarity (Creature_Rarity 0, 1, 2, 5 = queen). */
    private static final int[] RARITY_STARS = {1, 2, 3, 0, 0, 4};
    /** The Incrediballs: {StringID, rarity}. */
    private static long[][] creatures = new long[0][];
    private static final long START_DAY = 20773;         // 2026-11-17: the tree players grow from there

    private static final String[] NICKNAMES = {
            "Lumzilla", "TeensyKing", "Glob0x", "Murfy_Fan", "RayRay", "Bubble_Dreamer", "Kiwi", "Lumberjack",
            "PixelFox", "Nina", "Max", "Leo", "Jade", "Hugo", "Emma", "Lucas", "Chloé", "Noah", "Mia", "Tom",
            "Zoe", "Sam", "Lily", "Ethan", "Lola", "Theo", "Inès", "Jules", "Clara", "Enzo", "Sofia", "Nathan",
            "Manon", "Arthur", "Alice", "Gabriel", "Louise", "Ryan", "Anna", "Mateo", "Lucie", "Paul",
            "SpeedyLum", "EggHunter", "Incrediball", "NightRunner", "Captain_Lum", "Dragonfly", "Sunny",
            "Shadow", "Tornado", "MissLum", "SkyWalker", "Bouncy", "Sparky", "Nemo", "Pepper", "Mango",
            "Coco", "Biscuit", "Pumpkin", "Pirate", "Ninja", "Wizard", "Viking", "Zorro", "Rocket", "Comet",
    };

    /** Country of the non-local players, by weight (ISO codes, as the profiles' deviceCountry). */
    private static final String[] COUNTRIES = {
            "US", "US", "US", "US", "FR", "FR", "FR", "DE", "DE", "GB", "GB", "BR", "BR", "ES", "ES", "IT",
            "IT", "CA", "MX", "RU", "PL", "NL", "BE", "CH", "JP", "KR", "AU", "SE", "PT", "AR", "TR", "CN",
    };

    /** Costumes they wear (shop costumes anyone could have). */
    private static final String[] COSTUMES = {
            "Rayman", "Rayman", "Rayman", "Barbara", "Barbara", "Globox", "Teensy", "Rayman_Classic",
            "Rayman_Chevalier", "Rayman_Cromagnon", "Rayman_Zombie", "Rayman_Nu", "Rayman_Assassin",
            "Rayman_Dark", "Rayman_Demo", "Rayman_Werewolf", "Rayman_Raybeard", "Rayman_Spaceray",
            "Globox_Classic", "Globox_Red", "Globox_Zombie", "Globox_Nu", "Globox_Chevalier",
            "Barbara_Classic", "Barbara_braveHeart", "Barbara_Mexican", "Barbara_Olympus", "Barbara_Dark",
            "Teensy_Gold", "Teensy_Mago", "Teensy_Rayman", "Teensy_Rosebonbon", "Teensy_Bunny",
    };

    private FictionalPlayers() {
    }

    /** One fictional player. */
    static final class Player {
        final int index;
        final String pid;
        final String name;
        final String country;
        final long costume;

        Player(int index, String pid, String name, String country, long costume) {
            this.index = index;
            this.pid = pid;
            this.name = name;
            this.country = country;
            this.costume = costume;
        }

        JSONObject shortProfile() throws JSONException {
            JSONObject o = new JSONObject();
            o.put("pid", pid);
            o.put("name", name);
            o.put("deviceCountry", country);
            o.put("stars", treeStars(index));
            o.put("costume", costume);
            o.put("img", "");
            return o;
        }
    }

    static boolean isFictional(String pid) {
        return pid != null && pid.startsWith(PID_PREFIX);
    }

    static Player byPid(String pid) {
        try {
            return get(Integer.parseInt(pid.substring(PID_PREFIX.length())));
        } catch (RuntimeException e) {
            return null;
        }
    }

    static Player get(int index) {
        long h = hash(index, 0x51ED);
        String name;
        if ((h & 1) == 0) {
            name = defaultNamePrefix() + " " + (100000 + (h >>> 8) % 900000);
        } else {
            name = NICKNAMES[(int) ((h >>> 8) % NICKNAMES.length)];
            if (((h >>> 20) & 3) != 0) {
                name += (h >>> 24) % 100;
            }
        }
        String country = ((h >>> 32) & 3) == 0 ? playerCountry() : COUNTRIES[(int) ((h >>> 34) % COUNTRIES.length)];
        long costume = stringId(COSTUMES[(int) ((h >>> 40) % COSTUMES.length)]);
        return new Player(index, PID_PREFIX + index, name, country, costume);
    }

    /**
     * Stars of a player's Incrediballs = score of the tree ranking: 3 to 860, half of the players below
     * about 19 (260 m); it grows a little every day (up to +30% a year).
     */
    static long treeStars(int index) {
        double u = unit(hash(index, 0x7EE));
        double base = 3 * Math.exp(Math.pow(u, 1.7) * Math.log(860 / 3.0));
        double growth = 0.3 * unit(hash(index, 0x6E0));
        long days = Math.max(0, ServerState.today() - START_DAY);
        return Math.min(MAX_STARS, Math.round(base * (1 + growth * days / 365.0)));
    }

    static void loadCreatures(String json) {
        try {
            JSONArray a = new JSONArray(json);
            long[][] c = new long[a.length()][];
            for (int i = 0; i < a.length(); i++) {
                JSONObject o = a.getJSONObject(i);
                c[i] = new long[]{o.getLong("id"), o.getInt("rarity")};
            }
            creatures = c;
        } catch (JSONException e) {
            android.util.Log.e(OfflineServer.TAG, "bad creatures.json", e);
        }
    }

    /**
     * The player's Incrediballs (RO2_PersistentGameData_Universe::RLC_CreatureData {creatureId, count,
     * favorite, exhausted}): picked in a random order, the commons first, until they make the stars.
     */
    static JSONArray creatures(int index) throws JSONException {
        long target = treeStars(index);
        final int n = creatures.length;
        Integer[] order = new Integer[n];
        final double[] key = new double[n];
        for (int i = 0; i < n; i++) {
            order[i] = i;
            key[i] = RARITY_STARS[(int) creatures[i][1]] + 3.5 * unit(hash(index * 1000L + i, 0xC4EA));
        }
        java.util.Arrays.sort(order, (a, b) -> Double.compare(key[a], key[b]));
        JSONArray out = new JSONArray();
        long stars = 0;
        for (int k = 0; k < n && stars < target; k++) {
            long[] c = creatures[order[k]];
            JSONObject o = new JSONObject();
            o.put("creatureId", c[0]);
            o.put("count", 1);
            o.put("favorite", false);
            o.put("exhausted", false);
            out.put(o);
            stars += RARITY_STARS[(int) c[1]];
        }
        return out;
    }

    /** Score of a player in a ranking whose scores are spread around {@code typical}. */
    static long scoreAround(int index, long salt, double typical) {
        // log-normal: half of them below 90% of the typical score, a few far above
        double g = gaussian(hash(index, salt));
        return Math.max(1, Math.round(typical * 0.9 * Math.exp(0.45 * g)));
    }

    static List<Player> world() {
        List<Player> out = new ArrayList<>(WORLD);
        for (int i = 0; i < WORLD; i++) {
            out.add(get(i));
        }
        return out;
    }

    static String playerCountry() {
        String c = ProfileStore.get().optString("deviceCountry", "");
        return c.isEmpty() ? "FR" : c;
    }

    /** "AVENTURIER" from the player's own default name "AVENTURIER 614438" (else "ADVENTURER"). */
    static String defaultNamePrefix() {
        String n = ProfileStore.get().optString("privateName", "").trim();
        int sp = n.lastIndexOf(' ');
        if (sp > 0 && n.substring(sp + 1).matches("\\d+")) {
            return n.substring(0, sp);
        }
        return "ADVENTURER";
    }

    // --- deterministic randomness ------------------------------------------------------------

    private static long hash(long a, long b) {
        long x = a * 0x9E3779B97F4A7C15L + b * 0xC2B2AE3D27D4EB4FL + 0x165667B19E3779F9L;
        x ^= x >>> 33;
        x *= 0xFF51AFD7ED558CCDL;
        x ^= x >>> 33;
        x *= 0xC4CEB9FE1A85EC53L;
        x ^= x >>> 33;
        return x & Long.MAX_VALUE;
    }

    /** Uniform in [0, 1). */
    private static double unit(long h) {
        return (h >>> 11) / (double) (1L << 52);
    }

    /** Standard normal (Box-Muller). */
    private static double gaussian(long h) {
        double u1 = Math.max(1e-12, unit(h));
        double u2 = unit(hash(h, 0xB0C5));
        return Math.sqrt(-2 * Math.log(u1)) * Math.cos(2 * Math.PI * u2);
    }

    static long hashOf(long a, long b) {
        return hash(a, b);
    }

    /** ITF StringID (Bob Jenkins' lookup2 of the upper-cased text, initval 0), as tools/re/stringid.py. */
    static long stringId(String text) {
        byte[] k = text.toUpperCase(Locale.US).getBytes(java.nio.charset.StandardCharsets.ISO_8859_1);
        long a = 0x9E3779B9L, b = 0x9E3779B9L, c = 0;
        int i = 0, len = k.length;
        while (len - i >= 12) {
            a = (a + u32(k, i)) & 0xFFFFFFFFL;
            b = (b + u32(k, i + 4)) & 0xFFFFFFFFL;
            c = (c + u32(k, i + 8)) & 0xFFFFFFFFL;
            long[] m = mix(a, b, c);
            a = m[0];
            b = m[1];
            c = m[2];
            i += 12;
        }
        c = (c + k.length) & 0xFFFFFFFFL;
        int r = len - i;
        if (r >= 11) c = (c + ((k[i + 10] & 0xFFL) << 24)) & 0xFFFFFFFFL;
        if (r >= 10) c = (c + ((k[i + 9] & 0xFFL) << 16)) & 0xFFFFFFFFL;
        if (r >= 9) c = (c + ((k[i + 8] & 0xFFL) << 8)) & 0xFFFFFFFFL;
        if (r >= 8) b = (b + ((k[i + 7] & 0xFFL) << 24)) & 0xFFFFFFFFL;
        if (r >= 7) b = (b + ((k[i + 6] & 0xFFL) << 16)) & 0xFFFFFFFFL;
        if (r >= 6) b = (b + ((k[i + 5] & 0xFFL) << 8)) & 0xFFFFFFFFL;
        if (r >= 5) b = (b + (k[i + 4] & 0xFFL)) & 0xFFFFFFFFL;
        if (r >= 4) a = (a + ((k[i + 3] & 0xFFL) << 24)) & 0xFFFFFFFFL;
        if (r >= 3) a = (a + ((k[i + 2] & 0xFFL) << 16)) & 0xFFFFFFFFL;
        if (r >= 2) a = (a + ((k[i + 1] & 0xFFL) << 8)) & 0xFFFFFFFFL;
        if (r >= 1) a = (a + (k[i] & 0xFFL)) & 0xFFFFFFFFL;
        return mix(a, b, c)[2];
    }

    private static long u32(byte[] k, int i) {
        return (k[i] & 0xFFL) | ((k[i + 1] & 0xFFL) << 8) | ((k[i + 2] & 0xFFL) << 16) | ((k[i + 3] & 0xFFL) << 24);
    }

    private static long[] mix(long a, long b, long c) {
        final long m = 0xFFFFFFFFL;
        a = (a - b - c) & m; a ^= c >>> 13;
        b = (b - c - a) & m; b ^= (a << 8) & m;
        c = (c - a - b) & m; c ^= b >>> 13;
        a = (a - b - c) & m; a ^= c >>> 12;
        b = (b - c - a) & m; b ^= (a << 16) & m;
        c = (c - a - b) & m; c ^= b >>> 5;
        a = (a - b - c) & m; a ^= c >>> 3;
        b = (b - c - a) & m; b ^= (a << 10) & m;
        c = (c - a - b) & m; c ^= b >>> 15;
        return new long[]{a, b, c};
    }
}
