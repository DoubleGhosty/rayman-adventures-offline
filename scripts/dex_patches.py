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


PATCHES = {"classes4.dex": patch_classes4}
