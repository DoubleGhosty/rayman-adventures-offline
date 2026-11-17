"""Read files out of the game's UbiArt .ipk bundles (stored inside the OBB zip).

    python tools/re/ipk.py list  <bundle_android.ipk> [filter]
    python tools/re/ipk.py get   <bundle_android.ipk> <name-or-path-part> [out_file]

Bundle layout (big endian): magic 50 EC 12 BA, version, 2 x u32, base offset (u32 at 0x10), file count
(u32 at 0x14), ..., then one entry per file:
    u32 numOffsets, u32 size, u32 zsize, u64 timestamp, u64 offset (from base), u32 len + path,
    u32 len + name, u32 crc, u32 flags
Data of a compressed entry (zsize != 0) is LZMA1: 1 byte props, u32 dict size, raw stream.
"""
import lzma
import os
import struct
import sys
import zipfile

OBB = os.path.join(os.path.dirname(__file__), "..", "..", "apk", "main.2086.com.ubisoft.raymanadventures.obb")


def load(bundle):
    with zipfile.ZipFile(OBB) as z:
        return z.read(bundle)


def entries(d):
    base = struct.unpack_from(">I", d, 0x10)[0]
    count = struct.unpack_from(">I", d, 0x14)[0]
    # the entry table follows a short header; find the first entry by scanning for a plausible one
    p = 0x18
    while p < 0x200:
        try:
            n, size, zsize = struct.unpack_from(">III", d, p)
            plen = struct.unpack_from(">I", d, p + 28)[0]
            if n == 1 and 0 < plen < 300 and d[p + 32:p + 32 + plen].startswith(b"cache/"):
                break
        except struct.error:
            pass
        p += 1
    out = []
    for _ in range(count):
        n, size, zsize = struct.unpack_from(">III", d, p)
        off = struct.unpack_from(">Q", d, p + 20)[0]
        p += 28
        plen = struct.unpack_from(">I", d, p)[0]
        path = d[p + 4:p + 4 + plen].decode("latin1")
        p += 4 + plen
        nlen = struct.unpack_from(">I", d, p)[0]
        name = d[p + 4:p + 4 + nlen].decode("latin1")
        p += 4 + nlen + 8
        out.append((path + name, size, zsize, base + off))
    return out


def read(d, entry):
    _name, size, zsize, off = entry
    if not zsize:
        return d[off:off + size]
    raw = d[off:off + zsize]
    props = raw[0]
    filt = {"id": lzma.FILTER_LZMA1, "dict_size": struct.unpack("<I", raw[1:5])[0],
            "lc": props % 9, "lp": (props // 9) % 5, "pb": props // 45}
    return lzma.LZMADecompressor(format=lzma.FORMAT_RAW, filters=[filt]).decompress(raw[5:], max_length=size)


if __name__ == "__main__":
    cmd, bundle = sys.argv[1], sys.argv[2]
    d = load(bundle)
    es = entries(d)
    if cmd == "list":
        flt = sys.argv[3] if len(sys.argv) > 3 else ""
        for e in es:
            if flt in e[0]:
                print(e[1], e[0])
    else:
        e = next(e for e in es if sys.argv[3] in e[0])
        data = read(d, e)
        if len(sys.argv) > 4:
            open(sys.argv[4], "wb").write(data)
        print(e[0], len(data))
