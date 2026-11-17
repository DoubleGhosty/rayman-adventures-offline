"""Binary AndroidManifest.xml (AXML) patcher.

Declares the embedded offline server provider:

    <provider android:name="com.rayman.offline.OfflineServerProvider"
              android:exported="false"
              android:authorities="com.ubisoft.raymanadventures.offlineserver"/>

It works directly on the compiled binary XML (no apktool / resource rebuild):
two strings are appended to the string pool and the existing
<provider android:name="com.ubisoft.uaf.ZipFileContentProvider" .../> element
(same 3 attributes) is cloned with the new values.

Usage: patch_manifest(axml_bytes) -> new_axml_bytes   (idempotent)
"""
import struct

PROVIDER_CLASS = "com.rayman.offline.OfflineServerProvider"
PROVIDER_AUTHORITY = "com.ubisoft.raymanadventures.offlineserver"
TEMPLATE_CLASS = "com.ubisoft.uaf.ZipFileContentProvider"

RES_STRING_POOL = 0x0001
RES_XML_START_ELEMENT = 0x0102
RES_XML_END_ELEMENT = 0x0103
UTF8_FLAG = 0x100
TYPE_STRING = 0x03
ATTR_NAME = 0x01010003
ATTR_AUTHORITIES = 0x01010018


class StringPool:
    def __init__(self, data, off):
        (self.type, self.hsize, self.size, self.count, self.style_count, self.flags,
         self.strings_start, self.styles_start) = struct.unpack_from("<HHIIIIII", data, off)
        self.utf8 = bool(self.flags & UTF8_FLAG)
        offs = struct.unpack_from(f"<{self.count}I", data, off + self.hsize)
        base = off + self.strings_start
        self.strings = [self._decode(data, base + o) for o in offs]
        style_offs_pos = off + self.hsize + 4 * self.count
        self.style_offsets = list(struct.unpack_from(f"<{self.style_count}I", data, style_offs_pos))
        self.styles_blob = data[off + self.styles_start: off + self.size] if self.style_count else b""

    def _decode(self, d, p):
        if self.utf8:
            n = d[p]; p += 1
            if n & 0x80:
                p += 1
            blen = d[p]; p += 1
            if blen & 0x80:
                blen = ((blen & 0x7F) << 8) | d[p]; p += 1
            return d[p:p + blen].decode("utf-8")
        n = struct.unpack_from("<H", d, p)[0]; p += 2
        if n & 0x8000:
            n = ((n & 0x7FFF) << 16) | struct.unpack_from("<H", d, p)[0]; p += 2
        return d[p:p + 2 * n].decode("utf-16-le")

    def _encode(self, s):
        if self.utf8:
            b = s.encode("utf-8")
            def ln(n):
                return bytes([n]) if n < 0x80 else bytes([0x80 | (n >> 8), n & 0xFF])
            return ln(len(s)) + ln(len(b)) + b + b"\x00"
        b = s.encode("utf-16-le")
        n = len(b) // 2
        hdr = struct.pack("<H", n) if n < 0x8000 else struct.pack("<HH", 0x8000 | (n >> 16), n & 0xFFFF)
        return hdr + b + b"\x00\x00"

    def index(self, s):
        return self.strings.index(s)

    def add(self, s):
        if s in self.strings:
            return self.strings.index(s)
        self.strings.append(s)
        return len(self.strings) - 1

    def build(self):
        offsets, blob = [], b""
        for s in self.strings:
            offsets.append(len(blob))
            blob += self._encode(s)
        blob += b"\x00" * (-len(blob) % 4)
        count = len(self.strings)
        strings_start = self.hsize + 4 * count + 4 * self.style_count
        styles_start = strings_start + len(blob) if self.style_count else 0
        body = struct.pack(f"<{count}I", *offsets) + struct.pack(f"<{self.style_count}I", *self.style_offsets) + blob + self.styles_blob
        size = self.hsize + len(body)
        hdr = struct.pack("<HHIIIIII", RES_STRING_POOL, self.hsize, size, count, self.style_count,
                          self.flags, strings_start, styles_start)
        return hdr + b"\x00" * (self.hsize - 28) + body


def _chunks(data, start):
    off = start
    while off < len(data):
        ctype, hsize, size = struct.unpack_from("<HHI", data, off)
        yield off, ctype, size
        off += size


def _attrs(data, off):
    attr_start, attr_size, attr_count = struct.unpack_from("<HHH", data, off + 16 + 8)
    base = off + 16 + attr_start
    return [(base + i * attr_size) for i in range(attr_count)]


def patch_manifest(axml: bytes) -> bytes:
    data = bytearray(axml)
    ftype, fhsize, fsize = struct.unpack_from("<HHI", data, 0)
    assert ftype == 0x0003, "not a binary XML file"
    sp_off = fhsize
    pool = StringPool(data, sp_off)
    assert pool.type == RES_STRING_POOL
    if PROVIDER_CLASS in pool.strings:
        return bytes(axml)  # already patched

    # resource ids of attribute names (resource map maps string index -> attr id)
    rest_off = sp_off + pool.size
    res_ids = []
    for off, ctype, size in _chunks(data, rest_off):
        if ctype == 0x0180:
            res_ids = list(struct.unpack_from(f"<{(size - 8) // 4}I", data, off + 8))
            break

    def attr_id(name_idx):
        return res_ids[name_idx] if name_idx < len(res_ids) else None

    provider_idx = pool.index("provider")
    template_idx = pool.index(TEMPLATE_CLASS)

    # find template <provider> start element and its matching end element
    tmpl_start = tmpl_end = None
    depth = 0
    for off, ctype, size in _chunks(data, rest_off):
        if ctype == RES_XML_START_ELEMENT:
            name = struct.unpack_from("<I", data, off + 20)[0]
            if tmpl_start is None and name == provider_idx:
                for a in _attrs(data, off):
                    _, aname, raw = struct.unpack_from("<III", data, a)
                    if attr_id(aname) == ATTR_NAME and raw == template_idx:
                        tmpl_start, depth = off, 0
            if tmpl_start is not None and tmpl_end is None:
                depth += 1
        elif ctype == RES_XML_END_ELEMENT and tmpl_start is not None and tmpl_end is None:
            depth -= 1
            if depth == 0:
                tmpl_end = off + size
    assert tmpl_start is not None and tmpl_end is not None, "template provider not found"

    cls_idx = pool.add(PROVIDER_CLASS)
    auth_idx = pool.add(PROVIDER_AUTHORITY)

    clone = bytearray(data[tmpl_start:tmpl_end])
    patched = set()
    for a in _attrs(clone, 0):
        _, aname, raw = struct.unpack_from("<III", clone, a)
        rid = attr_id(aname)
        if rid == ATTR_NAME:
            new = cls_idx
        elif rid == ATTR_AUTHORITIES:
            new = auth_idx
        else:
            continue
        struct.pack_into("<I", clone, a + 8, new)          # rawValue
        size, res0, dtype = struct.unpack_from("<HBB", clone, a + 12)
        assert dtype == TYPE_STRING
        struct.pack_into("<I", clone, a + 16, new)         # typedValue.data
        patched.add(rid)
    assert patched == {ATTR_NAME, ATTR_AUTHORITIES}, patched

    new_pool = pool.build()
    out = (bytes(data[:sp_off]) + new_pool + bytes(data[rest_off:tmpl_end]) + bytes(clone)
           + bytes(data[tmpl_end:]))
    out = bytearray(out)
    struct.pack_into("<I", out, 4, len(out))
    return bytes(out)


if __name__ == "__main__":
    import sys, zipfile
    apk = sys.argv[1]
    with zipfile.ZipFile(apk) as z:
        src = z.read("AndroidManifest.xml")
    dst = patch_manifest(src)
    out = sys.argv[2] if len(sys.argv) > 2 else "AndroidManifest_patched.xml"
    open(out, "wb").write(dst)
    print(f"{len(src)} -> {len(dst)} bytes, written to {out}")
