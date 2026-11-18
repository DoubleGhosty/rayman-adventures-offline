# Developer guide

How *Rayman Adventures Offline* works, how to build it and how to debug it. The full reverse-engineering notes (addresses, formats, every endpoint, in French) are in [DOSSIER_TECHNIQUE.md](DOSSIER_TECHNIQUE.md); the November 2026 audit is in [AUDIT_2026-11-16.md](AUDIT_2026-11-16.md).

Target: *Rayman Adventures* **4.0.0.2086** for Android (ARM64, `com.ubisoft.raymanadventures`).

## How it works

The game talks to several Ubisoft services (UbiServices login, the "RLC" game server, the store, configuration). All of them are emulated by a small HTTP/HTTPS server that runs **inside the app**:

```
libuaf.so (the game, with its own curl + OpenSSL)
  getaddrinfo("*.ubi.com") --hook--> 127.0.0.1
  connect(:443 / :80)      --hook--> 127.0.0.1:18443 / :18080
                                       |
OfflineServerProvider (a ContentProvider, started by Android before any activity)
  OfflineServer: HTTP 18080 + HTTPS 18443 (self-signed certificate, accepted because
                 the game's TLS check is patched out)
```

Three kinds of changes make this work:

- **Native patches and hooks** in `lib/arm64-v8a/libuaf.so`: network redirection, TLS check removed, and small code caves where the game needed a server answer that can no longer be produced the same way (eggs, tickets, incubator, shop guards, events that come back every year, the title-screen login). See `scripts/*_hooks.py`.
- **The embedded server** (`offline_server/src/com/rayman/offline/`, compiled to an extra `classesN.dex`) answers every request the game makes. It keeps its state per save slot in the app's `files/rlc/` folder.
- **Small bytecode patches** to the game's own Java code (`scripts/dex_patches.py`): the Google Play Games sign-in is disabled.

The release APK also embeds the game data (the OBB): `res/raw/game.properties` says `package.main.Location = ASSET`, and the game's own installer copies `assets/*.obb` to `Android/obb/` on first launch.

### Server modules

| File | What it serves |
|---|---|
| `OfflineServer.java` | HTTP/TLS server, UbiServices (session, configuration), store catalog, news page, routing |
| `RlcApi.java` | Game server entry point (`/v<N>/<module>/<action>`), profile, session, save slots |
| `Slots.java`, `ProfileStore.java`, `ServerState.java` | Per-slot player profile and server-side state |
| `Incubator.java` | Incubator, hatching, elixirs, Charlie, magnifying glass |
| `Rewards.java` | Lucky ticket draws with Ubisoft's own weight tables |
| `DailyRewards.java`, `Challenges.java`, `Ghosts.java`, `Leaderboards.java` | Daily gift, daily challenge, ghosts, local leaderboards |
| `MiniEvents.java` | Weekend mini events |
| `SeasonalEvents.java` | Seasonal events calendar, sent as encrypted game globals |
| `Admin.java` | Debug endpoints (see below) |

### Seasonal events in short

The game ships with no event scheduled; Ubisoft used to override `enginedata/gameconfig/seasonaleventconfig.isg` through `gameglobals/getGameGlobals`. The server now sends 5 years of calendar in one answer: one override per event, each with a date condition, so the game picks the current event by itself at every launch. The answer is XXTEA-encrypted and base64-encoded, like Ubisoft's. The same answer also carries Ubisoft's own overrides bundled with the game (adventure durations, magnifying glass price, ticket weights, daily gifts: `mock_data/ubisoft_gameglobals.json`, from `tools/re/gameglobals.py`), because the game ignores its bundled globals once a newer download is cached. A marathon is the daily challenge in event mode: during one, the challenge reward also gives 150 event currency (`Challenges.MARATHON_CURRENCY`). Details, formats and keys are in DOSSIER_TECHNIQUE.md ("Événements saisonniers").

## Building

Ubisoft's files are not in the repository. Put them in place first:

| File | Where it comes from |
|---|---|
| `apk/base_original.apk` | The original 4.0.0.2086 APK |
| `apk/main.2086.com.ubisoft.raymanadventures.obb` | Its OBB (game data) |
| `binaries/libuaf_original.so` | `lib/arm64-v8a/libuaf.so` extracted from that APK |

Tools: Python 3 with `keystone-engine` and `capstone`, the Android SDK (build-tools 34 and platform 34; set `ANDROID_BUILD_TOOLS` if it isn't under `%LOCALAPPDATA%\Android\Sdk`), and a JDK (Android Studio's works).

```bash
python scripts/build_libuaf_offline.py     # patched libuaf.so -> binaries/libuaf_emulated.so (--debug adds logs)
python scripts/build_offline_server.py     # embedded server -> offline_server/build/classes.dex
python scripts/repackage_apk.py            # final signed APK, OBB embedded (--no-obb: light APK)
```

The signing key `apk/offline_testkey.jks` is created on the first build and is not in git. **Keep it**: every release must be signed with the same key, or players can't update without uninstalling (and losing their progress).

During development, `repackage_apk.py --no-obb` builds a 42 MB APK that installs much faster on a device that already has the OBB.

## Testing on a device

Development was done on Windows Subsystem for Android (rooted, `adb connect 127.0.0.1:58526`). With two adb devices listed, `export ANDROID_SERIAL=127.0.0.1:58526`.

- Server log: `adb logcat -s RaymanOffline` (every request and answer).
- Debug build logs: `adb logcat -s RaymanDbg RaymanITF` (module states, engine URLs). `python tools/re/annot.py` turns module vtables into class names.
- **Back up the player's save before any test** (the app data folder and `Android/data/<package>`), and restore it afterwards.

### Admin endpoints

After `adb forward tcp:18080 tcp:18080`:

| URL | Effect |
|---|---|
| `/offline/admin/profile`, `/state`, `/slots`, `/incubation` | Dump server-side data |
| `/offline/admin/seedEgg?creatureId=…&seconds=60` | Put an egg in the incubator |
| `/offline/admin/forceTicket?type=9&e0=2` | Next lucky ticket = this reward |
| `/offline/admin/drawTickets?type=4&n=100000` | Ticket draw statistics |
| `/offline/admin/resetDailyReward` | Daily gift available again |
| `/offline/admin/miniEvent?name=Mini%20Marathon&hours=2` | Run a mini event now |
| `/offline/admin/seasonalEvent?id=3&days=7` | Run seasonal event 3 now (`id=0`: back to the calendar) |
| `/offline/admin/challenge`, `/ageChallenges` | Daily challenge data, age stored scores by a day |

A new seasonal calendar reaches the game only through `userprofile/meta` sent after the title-screen login. Restart the game twice after forcing an event: the first launch downloads it, the second applies it.

## Reverse-engineering tools (`tools/re/`)

`syms.pkl` (symbols of `libuaf.so`) is built locally and not in git.

| Tool | Use |
|---|---|
| `rdis.py <symbol or addr> [size]` | Annotated disassembly (call targets, strings) |
| `callers.py <symbol or addr>` | Call sites of a function |
| `fields.py <SerializeImpl symbol>` | Field names an ITF class serializes |
| `all_requests.py` | Every game-server request the client can build |
| `memread.py` | Read and write the live game memory (root) |
| `ipk.py list/get <bundle.ipk> …` | Extract files from the game's `.ipk` bundles (inside the OBB) |
| `stringid.py <text>` | ITF StringID hash of a text or path |
| `gameglobals.py [out.json]` | Decrypt Ubisoft's bundled game globals and extract their overrides |
| `dump_ticket_weights.py` | Dump the lucky ticket weight tables from memory |

## Known limits and ideas

- Only tested on WSA, not yet on a real ARM64 phone.
