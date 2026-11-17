"""Read the live memory of the game on a rooted device (adb + su).

    from memread import Mem
    m = Mem()                 # attaches to com.ubisoft.raymanadventures
    m.base                    # libuaf.so load address
    m.q(addr), m.d(addr), m.read(addr, n)
"""
import os, struct, subprocess

PKG = "com.ubisoft.raymanadventures"
ENV = dict(os.environ, MSYS_NO_PATHCONV="1")


def _sh(cmd):
    return subprocess.run(["adb", "exec-out", f"su -c '{cmd}'"], capture_output=True, env=ENV).stdout


class Mem:
    def __init__(self):
        self.pid = _sh(f"pidof {PKG}").decode().strip()
        maps = _sh(f"grep libuaf /proc/{self.pid}/maps").decode().splitlines()
        self.base = int(maps[0].split("-")[0], 16)
        self.cache = {}

    def read(self, addr, n):
        page = 0x1000
        out = b""
        a = addr
        while a < addr + n:
            p = a & ~(page - 1)
            if p not in self.cache:
                self.cache[p] = _sh(f"dd if=/proc/{self.pid}/mem bs=4096 skip={p // page} count=1 2>/dev/null")
            chunk = self.cache[p][a - p: min(page, addr + n - p)]
            if not chunk:
                raise IOError(f"cannot read {a:#x}")
            out += chunk
            a = p + page if a - p + len(chunk) >= page else a + len(chunk)
        return out[:n]

    def q(self, addr):
        return struct.unpack("<Q", self.read(addr, 8))[0]

    def d(self, addr):
        return struct.unpack("<I", self.read(addr, 4))[0]


def write_u32(mem, addr, value):
    """Writes a little-endian u32 into the game's memory (root)."""
    data = struct.pack("<I", value)
    esc = "".join(f"\\x{b:02x}" for b in data)
    _sh(f"printf \"{esc}\" | dd of=/proc/{mem.pid}/mem bs=1 seek={addr} count=4 conv=notrunc 2>/dev/null")
    mem.cache.clear()


def write_bytes(mem, addr, data):
    """Writes raw bytes into the game's memory (root)."""
    esc = "".join(f"\\x{b:02x}" for b in data)
    _sh(f"printf \"{esc}\" | dd of=/proc/{mem.pid}/mem bs=1 seek={addr} count={len(data)} conv=notrunc 2>/dev/null")
    mem.cache.clear()
