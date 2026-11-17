"""Ubisoft's game globals bundled with the game (enginedata/online/gameglobals.isg.ckd, in
bundle_android.ipk): decrypt them and print their overrides.

    python tools/re/gameglobals.py [out.json]

The cooked file is an online::gameGlobalsContainer: its "data" field is encrypted with
StartEncryption (XXTEA, little-endian words, key 2d8441f7 e30865fc c9f5b992 03bb7669, zero bytes
dropped after decoding), which gives the base64 of the binary-serialized data. Inside, each override's "json" is a JSON text (template fields +
_CLASS_NAME), keyed by the StringID of the template path (tools/re/stringid.py).
out.json gets {"<path StringID>": "<json text>"} for the server (mock_data/ubisoft_gameglobals.json).
"""
import base64
import json
import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ipk  # noqa: E402
from stringid import stringid  # noqa: E402

KEY = (0x2d8441f7, 0xe30865fc, 0xc9f5b992, 0x03bb7669)
DELTA = 0x9e3779b9
M = 0xFFFFFFFF
PATHS = ["enginedata/online/dynamicstore.isg", "enginedata/gameconfig/inapppurchaseconfig.isg",
         "enginedata/gameconfig/seasonaleventconfig.isg"]


def xxtea_decrypt(v):
    n = len(v)
    rounds = 6 + 52 // n
    s = (rounds * DELTA) & M
    y = v[0]
    while s:
        e = (s >> 2) & 3
        for p in range(n - 1, -1, -1):
            z = v[p - 1] if p > 0 else v[n - 1]
            mx = (((z >> 5) ^ (y << 2)) + ((y >> 3) ^ (z << 4))) ^ ((s ^ y) + (KEY[(p & 3) ^ e] ^ z))
            v[p] = (v[p] - mx) & M
            y = v[p]
        s = (s - DELTA) & M
    return v


def plain():
    b = ipk.load("bundle_android.ipk")
    d = ipk.read(b, next(e for e in ipk.entries(b) if e[0].endswith("online/gameglobals.isg.ckd")))
    size = struct.unpack_from(">I", d, 0x18)[0]
    enc = d[0x1c:0x1c + size]
    words = list(struct.unpack("<%dI" % (len(enc) // 4), enc[:len(enc) // 4 * 4]))
    text = struct.pack("<%dI" % len(words), *xxtea_decrypt(words)).replace(b"\0", b"")
    return base64.b64decode(text)       # the decrypted text is base64 of the binary-serialized data


def overrides(p):
    """{path StringID: json text} for every override JSON found after its key."""
    out = {}
    for m in re.finditer(rb"\{\n[ -~\n\t]{20,}?\n\}", p):
        text = m.group().decode()
        json.loads(text)
        before = p[:m.start()]
        key = None
        for path in PATHS:
            k = struct.pack(">I", stringid(path))
            i = before.rfind(k)
            if i >= 0 and (key is None or i > key[1]):
                key = (stringid(path), i)
        out[str(key[0])] = text
    return out


if __name__ == "__main__":
    o = overrides(plain())
    for k, v in o.items():
        j = json.loads(v)
        print(k, j.get("_CLASS_NAME"), sorted(j)[:8], "...")
    if len(sys.argv) > 1:
        with open(sys.argv[1], "w", encoding="utf-8") as f:
            json.dump(o, f, indent=1)
