"""Bytecode patches of the game's own dex files (applied by repackage_apk.py).

1. No Google sign-in (classes4.dex, com.ubisoft.uaf.social.gameservices.GameServicesHelper.connect()).
   The game signed in to Google Play Games at every launch (silentSignIn, then the account chooser).
   Google only accepts the APK signed by Ubisoft, and ours is re-signed, so the sign-in can never
   succeed: it only showed the chooser. connect() is the only entry point (onStart at launch,
   beginUserInitiatedSignIn from buttons); its body becomes what the game itself does when it must
   not connect (onStart with mConnectOnStart = false):
       const/4 v1, 0
       invoke-virtual {v3, v1}, GameServicesHelper.notifyListener(Z)V   -> listener.onSignInCancelled()
       return-void
   The game's own achievements (RLC_MissionManager, rewards) are local and unaffected; only the copy
   to Google Play Games achievements, which could not work, is gone.

2. Rewarded videos without ads (classes4.dex, com.ubisoft.uaf.GameActivity). The "watch a video"
   buttons (daily gift x2, revive, free wheel spin, adventure time extension, elixirs...) call
   MobileSDKModule::playMoPubVideo -> GameActivity.playMoPubVideo(int context), which showed an
   AppLovin MAX rewarded ad (or waited 20 s for one). When the player had watched it, the listener
   (GameActivity$3.onUserRewarded) posted GameActivity$3$1 on the UI thread, which calls
   UAFJNILib.onMPRewardedVideoFinished(true, moPubContext) -> RLC_InventoryManager::onVideoRewardedViewed.
   playMoPubVideo now does exactly that, without any ad:
       iput v4, v3, GameActivity.moPubContext:I
       new-instance v0, GameActivity$3 ; invoke-direct {v0, v3}, GameActivity$3.<init>(GameActivity)
       new-instance v1, GameActivity$3$1 ; invoke-direct {v1, v0}, GameActivity$3$1.<init>(GameActivity$3)
       invoke-virtual {v3, v1}, GameActivity.runOnUiThread(Runnable)
       return-void
   so the reward arrives a moment later, as after a real video. hasRewardedVideoAvailable() returns
   true (the buttons stay usable without an ad network).
"""
import hashlib
import struct
import zlib

CONNECT_CODE_ITEM = 0x1D0BE0
CONNECT_ORIG = bytes.fromhex("6e103f2f03000a00121 11a026a1538000b006e20412f1300".replace(" ", ""))
CONNECT_NEW = bytes.fromhex("1201" "6e20412f1300" "0e00")


def _fix_header(dex):
    dex[12:32] = hashlib.sha1(dex[32:]).digest()
    dex[8:12] = struct.pack("<I", zlib.adler32(bytes(dex[12:])) & 0xFFFFFFFF)


def patch_classes4(data):
    dex = bytearray(data)
    off = CONNECT_CODE_ITEM
    regs, ins, outs, tries, _dbg, n = struct.unpack_from("<HHHHII", dex, off)
    assert (regs, ins, tries, n) == (4, 1, 0, 50), "classes4.dex: unexpected GameServicesHelper.connect()"
    assert bytes(dex[off + 16:off + 16 + len(CONNECT_ORIG)]) == CONNECT_ORIG, "classes4.dex: connect() bytes differ"
    # same size (code items are laid out back to back): the rest of the method becomes nops
    dex[off + 16:off + 16 + n * 2] = CONNECT_NEW + bytes(n * 2 - len(CONNECT_NEW))
    _fix_header(dex)
    return bytes(dex)


PLAY_VIDEO_CODE_ITEM = 0x1C2C34     # GameActivity.playMoPubVideo(I)V
PLAY_VIDEO_ORIG = bytes.fromhex("5934bd24" "54349224" "39040300" "0e00")
PLAY_VIDEO_NEW = bytes.fromhex(
    "5934bd24"          # iput v4, v3, moPubContext
    "2200030b"          # new-instance v0, GameActivity$3
    "7020602b3000"      # invoke-direct {v0, v3}, GameActivity$3.<init>
    "2201ff0a"          # new-instance v1, GameActivity$3$1
    "7020562b0100"      # invoke-direct {v1, v0}, GameActivity$3$1.<init>
    "6e20232c1300"      # invoke-virtual {v3, v1}, runOnUiThread
    "0e00")             # return-void
HAS_VIDEO_CODE_ITEM = 0x1BFD30      # GameActivity.hasRewardedVideoAvailable()Z
HAS_VIDEO_ORIG = bytes.fromhex("54309224" "1201")
HAS_VIDEO_NEW = bytes.fromhex("1210" "0f00")  # const/4 v0, 1 ; return v0


def _replace_body(dex, off, shape, orig, new, what):
    regs, ins, outs, tries, _dbg, n = struct.unpack_from("<HHHHII", dex, off)
    assert (regs, ins, tries, n) == shape, f"classes4.dex: unexpected {what}"
    assert bytes(dex[off + 16:off + 16 + len(orig)]) == orig, f"classes4.dex: {what} bytes differ"
    assert len(new) <= n * 2
    dex[off + 16:off + 16 + n * 2] = new + bytes(n * 2 - len(new))


def patch_classes4_all(data):
    dex = bytearray(patch_classes4(data))
    _replace_body(dex, PLAY_VIDEO_CODE_ITEM, (5, 2, 0, 61), PLAY_VIDEO_ORIG, PLAY_VIDEO_NEW,
                  "GameActivity.playMoPubVideo")
    _replace_body(dex, HAS_VIDEO_CODE_ITEM, (4, 1, 0, 17), HAS_VIDEO_ORIG, HAS_VIDEO_NEW,
                  "GameActivity.hasRewardedVideoAvailable")
    _fix_header(dex)
    return bytes(dex)


PATCHES = {"classes4.dex": patch_classes4_all}
