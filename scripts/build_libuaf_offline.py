# Auto-generated offline patch script for libuaf.so (Rayman Adventures v4.0.0.2086)
import os, sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BIN_DIR = os.path.join(BASE_DIR, '..', 'binaries')
ORIG_PATH = os.path.join(BIN_DIR, 'libuaf_original.so')
OUTPUT_PATH = os.path.join(BIN_DIR, 'libuaf_emulated.so')

if not os.path.exists(ORIG_PATH):
    print(f"Error: Original binary not found at {ORIG_PATH}")
    sys.exit(1)

with open(ORIG_PATH, "rb") as f:
    data = bytearray(f.read())

print(f"Read {len(data)} bytes from {ORIG_PATH}")

PATCHES = {
    # 0xd6a240..0xd6a28b: code cave of the legacy patches (null-checking thunks used by 0x1a1d650 /
    # 0x1a1d654, local HatchSimulation for adventure eggs used by 0x16b2e04). The rest of the old cave
    # (0xd6a290.., dynamicStore::isItemOfType guessing) is gone with its hook, see below; since
    # 2026-11-16 0xd6a290.. holds the lucky ticket egg picker (scripts/ticket_hooks.py).
    0xd6a240: bytes.fromhex("40"),
    0xd6a243: bytes.fromhex("b42315fc17"),
    0xd6a24a: bytes.fromhex("8052c0035fd640"),
    0xd6a253: bytes.fromhex("b47b13fc17"),
    0xd6a25a: bytes.fromhex("80d2c0035fd62101"),
    0xd6a263: bytes.fromhex("54e00313aae1031a2ae2031b2a0301261e04"),
    0xd6a276: bytes.fromhex("805215a02494f403"),
    0xd6a27f: bytes.fromhex("2ae2222514e1222514e0222514"),
    # (0x1646480, RLC_InAppPurchaseManager::tryBuy "not enough gems" check -> nop, and
    #  0x1841cb8, dynamicStore::getUserGems -> "return 50000", were dropped: gems are real again,
    #  read from the inventory stock that the catalogue ITEM_TYPE fix made the game create.)
    0x16b2e04: bytes.fromhex("17ddda17"),
    0x16b3bf4: bytes.fromhex("1900"),
    0x16b3bf7: bytes.fromhex("14"),
    0x170aad4: bytes.fromhex("1f2003d5"),
    0x175ca54: bytes.fromhex("c0035fd6"),
    # (0x1835a58, dynamicStore::isItemOfType -> item-id guessing cave at 0xd6a290, was dropped:
    #  it made every elixir an easter-egg stock. The catalogue now carries the real ITEM_TYPE
    #  attributes, see build_offline_server.write_store_catalog.)
    0x1a1d650: bytes.fromhex("fc32cd"),
    0x1a1d654: bytes.fromhex("ff32cd"),
    0x1a9dcb0: bytes.fromhex("3f000171600000543f44017141000054bf7b00f9"),
}

for off, patch in PATCHES.items():
    data[off:off+len(patch)] = patch

# --- UbiServices TLS: its own OpenSSL verify callback (with certificate pinning) ---
# OpenSSLCertificateValidator::configureSSL installs certVerifyCallback via
# SSL_CTX_set_cert_verify_callback; that callback returns 1 (accept) right away when
# isVerifyRequired() is false. Without this, the login/session requests to
# public-ubiservices.ubi.com abort the handshake (TLSV1_ALERT_UNKNOWN_CA) against
# the embedded server's self-signed certificate.
ONLINE_PATCHES = {
    # OpenSSLCertificateValidator::isVerifyRequired: add x0,#8; b ... -> mov w0,#0; ret
    0x1c03b54: (bytes.fromhex("00200091fdffff17"), bytes.fromhex("00008052c0035fd6")),
}
# --- Game server ("NodeJs" RLC API: incubator, tickets, rewards, profile...) ---
# GameServerModule::updateConnecting falls back to the hard-coded "https://rc.ubi.com"
# when no NodeJsConfig space entity is provided (our server returns no entities).
# Game requests (online::HttpModule_UbiServicesSDK -> ubiservices HttpClient / curl) then go
# to this base URL. Same-length replacement "http://rc2.ubi.com": plain HTTP (no TLS needed),
# resolved to 127.0.0.1 by the getaddrinfo hook, port 80 remapped to 18080 by the connect hook.
# (An IPv6 literal "http://[::1]:18080" is NOT accepted by the ubiservices HTTP client.)
# Only the Java NetworkController error-log calls (/v2/log) cannot resolve this host: harmless.
ONLINE_PATCHES[0x1e1423c] = (b"https://rc.ubi.com\x00", b"http://rc2.ubi.com\x00")

# GameServerModule::updateConnecting: in prod the environment name starts empty and is only
# filled from the "nodeConfig" space entity (redirections). An empty name aborts the connection
# ("Connexion au serveur..." forever). Default it to "Prod" (existing string at 0x1df07d8) so the
# module connects to the default URL above without needing that entity.
#   0x17fb2c8: adrp x1, 0x1e9d000; add x1, x1, #0x906 ("")  ->  adrp x1, 0x1df0000; add x1, x1, #0x7d8 ("Prod")
ONLINE_PATCHES[0x17fb2c8] = (bytes.fromhex("013500d021182491"), bytes.fromhex("a12f00b021601f91"))

# GameServerModule::verifySignature: game-server answers carry an RSA signature ("rlc-hash"
# header over body + ";id=" + rlc-msg-id). Ubisoft's private key is gone -> always valid.
#   0x17f01e0: sub sp, sp, #0xe0; stp x19, x20, [sp]  ->  mov w0, #1; ret
ONLINE_PATCHES[0x17f01e0] = (bytes.fromhex("ff8303d1f35300a9"), bytes.fromhex("20008052c0035fd6"))

# RLC_AdventureManager::onGameServerRequestDone (PlayerCreatures answer): when the server's
# profileId differs from the local pid, the original code skips the whole update block, which
# leaves the "waiting for creature sync" flag (+0x69c) set -> every incubator action fails with
# error 0x10040602. The embedded server sends a distinct profileId on purpose (to skip
# reconcileServerCreatures, which would replace the local creatures); fall through into the
# update block instead of jumping over it.
#   0x16e4190: b 0x16e4220  ->  nop
ONLINE_PATCHES[0x16e4190] = (bytes.fromhex("24000014"), bytes.fromhex("1f2003d5"))

# (Removed 16/11/2026) 0x175b1e0 RLC_Incubator::beforeDropEggOnIncubator and 0x17c1188
# tryElixirUtilisation "hatch now": the original code works locally while the player is in the
# onboarding (hasAllOnBoardingCreatures / isOnBoarding) and through the game server afterwards.
# Forcing the server path broke the tutorial ("Glisse l'oeuf dans l'incubateur" ->
# "Echec de la connexion au serveur"): during onboarding the game server is not connected yet.
# The original tests are kept. (The very first legacy patch list nopped them, which made every egg
# local even after onboarding - the "egg disappears" bug; that stays fixed.) A tutorial egg unknown
# to the server is kept and hatched locally thanks to the HTTP 410 handling (incubator_hooks.py).

# RLC_GS_Leaderboard::initialiseOnlineProfiles ("Classement" screen): when the leaderboard answers
# name no other player (only the local player, who is left out of that list), the code marks the
# lists done (LeaderboardManager+0x101, clearFriends) and shows "Echec de la connexion au serveur"
# (text 0x1d6); after its OK the screen shows the player alone. Offline the player is always alone:
# keep that path but skip the popup (TRCManagerAdapter::addMessage).
#   0x169bff8: adrp x0, ... (start of the popup code)  ->  b 0x169c06c (after it)
ONLINE_PATCHES[0x169bff8] = (bytes.fromhex("007100f0"), bytes.fromhex("1d000014"))

# Ads: no forced interstitials, rewarded videos kept (player's choice, 16/11/2026).
# RO2_PersistentGameData_IAP::isInterstitialDisabled() is true when the player owns the "no ads"
# purchase; it is the only gate of MobileSDKModule::cacheInterstitials and ::showMoPubInterstitial
# (score recap, runner challenge, creature tree, UAF_resume). Always true = interstitials never
# loaded nor shown. Rewarded videos ("Regarder une publicite" for gems, food, tickets...) go through
# MobileSDKModule::playMoPubVideo / cacheRewardedVideos and are not affected.
#   0x147294c: sub sp, sp, #0x30; stp x19, x20, [sp]  ->  mov w0, #1; ret
ONLINE_PATCHES[0x147294c] = (bytes.fromhex("ffc300d1f35300a9"), bytes.fromhex("20008052c0035fd6"))

# Title screen "Actualites" (news): RO2_GS_MainMenu::openNewsWebView -> MobileSDKModule::openNewsURL
# opens GameServerModule::getNewsURL() = "%s/v1/news/%d" (game server base URL, language) in the
# game's WebView (Java rlcWebView). The WebView resolves hosts with Android's DNS, outside the native
# hooks: "http://rc2.ubi.com" does not resolve and the game showed "Echec de la connexion au serveur".
# New format string (in the free bytes after the lucky ticket cave) that points at the embedded server,
# "%.0s" swallows the base URL argument: http://127.0.0.1:18080/v1/news/<language> (OfflineServer).
#   0x17ef014: adrp x1, 0x1e14000; add x1, x1, #0x1f5  ->  adrp x1, 0xe0b000; add x1, x1, #0
NEWS_URL_FORMAT = b"http://127.0.0.1:18080%.0s/v1/news/%d\x00"
ONLINE_PATCHES[0xE0B000] = (bytes(len(NEWS_URL_FORMAT)), NEWS_URL_FORMAT)
ONLINE_PATCHES[0x17ef014] = (bytes.fromhex("213100b021d40791"), bytes.fromhex("e1b0ff9021000091"))

for off, (orig, patch) in ONLINE_PATCHES.items():
    assert data[off:off+len(orig)] == orig, f"unexpected bytes at {off:#x}"
    data[off:off+len(patch)] = patch
print("Applied UbiServices TLS bypass + game server URL redirect.")

# --- Standalone networking: getaddrinfo/connect hooks (see scripts/net_hooks.py) ---
sys.path.insert(0, BASE_DIR)
from net_hooks import NET_HOOK_PATCHES, CAVE, PLT_GETADDRINFO, PLT_CONNECT

cave_blob = NET_HOOK_PATCHES[CAVE]
assert data[CAVE:CAVE + len(cave_blob)] == bytes(len(cave_blob)), "code cave is not empty"
for plt in (PLT_GETADDRINFO, PLT_CONNECT):  # must still be "adrp x16, <GOT page>"
    assert int.from_bytes(data[plt:plt + 4], "little") & 0x9F00001F == 0x90000010, f"unexpected PLT stub at {plt:#x}"
for off, patch in NET_HOOK_PATCHES.items():
    data[off:off+len(patch)] = patch
print(f"Applied network redirection hooks ({len(cave_blob)} bytes cave at {CAVE:#x}).")

# --- Incubator: keep eggs the server does not know about (see scripts/incubator_hooks.py) ---
from incubator_hooks import assemble as assemble_incubator_hooks, CAVE as INC_CAVE
inc = assemble_incubator_hooks(data)
assert data[INC_CAVE:INC_CAVE + len(inc[INC_CAVE])] == bytes(len(inc[INC_CAVE])), "incubator cave not empty"
for off, patch in inc.items():
    data[off:off + len(patch)] = patch
print(f"Applied incubator hooks ({len(inc[INC_CAVE])} bytes cave at {INC_CAVE:#x}).")

# --- Lucky ticket eggs: the game picks the creature of the drawn rarity (scripts/ticket_hooks.py) ---
from ticket_hooks import assemble as assemble_ticket_hooks, CAVE as TICKET_CAVE
tk = assemble_ticket_hooks(data)
assert data[TICKET_CAVE:TICKET_CAVE + len(tk[TICKET_CAVE])] == bytes(len(tk[TICKET_CAVE])), "ticket cave not empty"
for off, patch in tk.items():
    data[off:off + len(patch)] = patch
print(f"Applied lucky ticket hooks ({len(tk[TICKET_CAVE])} bytes cave at {TICKET_CAVE:#x}).")

# --- Magnifying glass / Charlie eggs: the game picks the creature (scripts/egg_pick_hooks.py) ---
from egg_pick_hooks import assemble as assemble_egg_pick_hooks, CAVE as EGG_CAVE
eg = assemble_egg_pick_hooks(data)
assert data[EGG_CAVE:EGG_CAVE + len(eg[EGG_CAVE])] == bytes(len(eg[EGG_CAVE])), "egg pick cave not empty"
for off, patch in eg.items():
    data[off:off + len(patch)] = patch
print(f"Applied egg pick hooks ({len(eg[EGG_CAVE])} bytes cave at {EGG_CAVE:#x}).")

# --- Shop guards: missing real-money packs return false instead of crashing (scripts/store_hooks.py) ---
from store_hooks import assemble as assemble_store_hooks, CAVE as STORE_CAVE
sh = assemble_store_hooks(data)
assert data[STORE_CAVE:STORE_CAVE + len(sh[STORE_CAVE])] == bytes(len(sh[STORE_CAVE])), "store cave not empty"
for off, patch in sh.items():
    data[off:off + len(patch)] = patch
print(f"Applied store hooks ({len(sh[STORE_CAVE])} bytes cave at {STORE_CAVE:#x}).")

# --- Seasonal events that come back every year (scripts/event_hooks.py) ---
from event_hooks import assemble as assemble_event_hooks, CAVE as EVENT_CAVE
ev = assemble_event_hooks(data)
assert data[EVENT_CAVE:EVENT_CAVE + len(ev[EVENT_CAVE])] == bytes(len(ev[EVENT_CAVE])), "event cave not empty"
for off, patch in ev.items():
    data[off:off + len(patch)] = patch
print(f"Applied seasonal event hooks ({len(ev[EVENT_CAVE])} bytes cave at {EVENT_CAVE:#x}).")

# --- Title-screen login: UbiServices not disconnected right after connecting (scripts/login_hooks.py) ---
from login_hooks import assemble as assemble_login_hooks
for off, patch in assemble_login_hooks(data).items():
    data[off:off + len(patch)] = patch
print("Applied login hook (no forced UbiServices disconnection).")

if "--debug" in sys.argv:
    from debug_hooks import assemble as assemble_debug_hooks
    dbg = assemble_debug_hooks()
    for off, patch in dbg.items():
        if off == 0xE0A200:  # debug code cave must be untouched zeros
            assert data[off:off + len(patch)] == bytes(len(patch)), "debug cave not empty"
        data[off:off + len(patch)] = patch
    print(f"DEBUG build: {len(dbg) - 1} logging hooks installed (adb logcat -s RaymanDbg).")

with open(OUTPUT_PATH, "wb") as f:
    f.write(data)

print(f"Successfully built {OUTPUT_PATH} ({len(data)} bytes) with {len(PATCHES)} patch regions applied!")
