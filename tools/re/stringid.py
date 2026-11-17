"""ITF StringID of a text (ITF::StrToCRC_Template<1>, 0x18ae1b0): Bob Jenkins' lookup2 hash of the
upper-cased bytes, initval 0. Paths hash their "dir/name.ext" text (Path::getStringID).

    python tools/re/stringid.py enginedata/gameconfig/seasonaleventconfig.isg
"""
import sys

M = 0xFFFFFFFF


def _mix(a, b, c):
    a = (a - b - c) & M; a ^= c >> 13
    b = (b - c - a) & M; b ^= (a << 8) & M
    c = (c - a - b) & M; c ^= b >> 13
    a = (a - b - c) & M; a ^= c >> 12
    b = (b - c - a) & M; b ^= (a << 16) & M
    c = (c - a - b) & M; c ^= b >> 5
    a = (a - b - c) & M; a ^= c >> 3
    b = (b - c - a) & M; b ^= (a << 10) & M
    c = (c - a - b) & M; c ^= b >> 15
    return a, b, c


def stringid(text):
    k = text.upper().encode("latin1") if isinstance(text, str) else bytes(text).upper()
    a = b = 0x9E3779B9
    c = 0
    n = len(k)
    i = 0
    while n - i >= 12:
        a = (a + k[i] + (k[i + 1] << 8) + (k[i + 2] << 16) + (k[i + 3] << 24)) & M
        b = (b + k[i + 4] + (k[i + 5] << 8) + (k[i + 6] << 16) + (k[i + 7] << 24)) & M
        c = (c + k[i + 8] + (k[i + 9] << 8) + (k[i + 10] << 16) + (k[i + 11] << 24)) & M
        a, b, c = _mix(a, b, c)
        i += 12
    c = (c + n) & M
    r = k[i:]
    for j, shift in ((10, 24), (9, 16), (8, 8)):
        if len(r) > j:
            c = (c + (r[j] << shift)) & M
    for j in range(7, 3, -1):
        if len(r) > j:
            b = (b + (r[j] << ((j - 4) * 8))) & M
    for j in range(3, -1, -1):
        if len(r) > j:
            a = (a + (r[j] << (j * 8))) & M
    return _mix(a, b, c)[2]


if __name__ == "__main__":
    for t in sys.argv[1:]:
        print(f"{stringid(t):#010x} {stringid(t)} {t}")
