# Native network redirection hooks for libuaf.so (Rayman Adventures v4.0.0.2086)
#
# Goal: make the APK fully standalone (no root, no hosts file, no PC mock server).
#
#   getaddrinfo(node, ...)  : any host ending in "ubi.com" is resolved as "127.0.0.1"
#   connect(fd, addr, len)  : AF_INET 127.0.0.1:80  -> 127.0.0.1:18080
#                             AF_INET 127.0.0.1:443 -> 127.0.0.1:18443
#
# Ports 18080 / 18443 are served by the embedded Java server
# (com.rayman.offline.OfflineServerProvider, started automatically at app launch).
# Unprivileged apps cannot bind ports < 1024, hence the port remap.
#
# Implementation: the PLT stubs of getaddrinfo / connect are replaced by a branch
# into a code cave (zero-filled, unreferenced area of .text). The hooks then jump
# to the real libc function through the original GOT slot.
#
# Usage:
#   python scripts/net_hooks.py          -> prints the patch table (needs keystone-engine)
#   build_libuaf_offline.py imports NET_HOOK_PATCHES (pre-assembled, no dependency)

CAVE = 0xE0A080            # inside zero run 0xe0a05c..0xe0b050 (verified: no branch targets it)
PLT_GETADDRINFO = 0xC6EB80
PLT_CONNECT = 0xC6E980
GOT_PAGE = 0x24A7000
GOT_GETADDRINFO_OFF = 0x478
GOT_CONNECT_OFF = 0x378

HTTP_PORT = 18080
HTTPS_PORT = 18443


def _htons_le16(port):
    """Value of a network-order u16 port when read with a little-endian ldrh."""
    return ((port & 0xFF) << 8) | (port >> 8)


ASM = f"""
hook_getaddrinfo:
    cbz     x0, gai_real
    mov     x9, x0
gai_len:
    ldrb    w10, [x9], #1
    cbnz    w10, gai_len
    sub     x9, x9, x0
    sub     x9, x9, #1              // x9 = strlen(node)
    cmp     x9, #7
    b.lo    gai_real
    add     x10, x0, x9
    sub     x10, x10, #7            // x10 = node + len - 7
    adr     x11, s_ubicom
    mov     x12, #0
gai_cmp:
    ldrb    w13, [x10, x12]
    orr     w13, w13, #0x20         // lowercase (keeps '.')
    ldrb    w14, [x11, x12]
    cmp     w13, w14
    b.ne    gai_real
    add     x12, x12, #1
    cmp     x12, #7
    b.ne    gai_cmp
    adr     x0, s_loopback
gai_real:
    adrp    x16, {GOT_PAGE:#x}
    ldr     x17, [x16, #{GOT_GETADDRINFO_OFF:#x}]
    br      x17

hook_connect:
    cbz     x1, con_real
    ldrh    w9, [x1]
    cmp     w9, #2                  // AF_INET
    b.ne    con_real
    ldr     w9, [x1, #4]
    movz    w10, #0x007f
    movk    w10, #0x0100, lsl #16   // 127.0.0.1 in memory order
    cmp     w9, w10
    b.ne    con_real
    ldrh    w9, [x1, #2]
    mov     w11, #0x5000            // htons(80)
    cmp     w9, w11
    b.eq    con_http
    mov     w11, #0xbb01            // htons(443)
    cmp     w9, w11
    b.eq    con_https
    b       con_real
con_http:
    mov     w12, #{_htons_le16(HTTP_PORT):#x}
    b       con_redirect
con_https:
    mov     w12, #{_htons_le16(HTTPS_PORT):#x}
con_redirect:
    stp     x29, x30, [sp, #-32]!
    mov     x29, sp
    ldp     x9, x10, [x1]
    stp     x9, x10, [sp, #16]
    strh    w12, [sp, #18]
    add     x1, sp, #16
    adrp    x16, {GOT_PAGE:#x}
    ldr     x17, [x16, #{GOT_CONNECT_OFF:#x}]
    blr     x17
    ldp     x29, x30, [sp], #32
    ret
con_real:
    adrp    x16, {GOT_PAGE:#x}
    ldr     x17, [x16, #{GOT_CONNECT_OFF:#x}]
    br      x17
"""

STRINGS = [("s_ubicom", b"ubi.com\x00"), ("s_loopback", b"127.0.0.1\x00")]


def assemble():
    import keystone
    ks = keystone.Ks(keystone.KS_ARCH_ARM64, keystone.KS_MODE_LITTLE_ENDIAN)
    src = ASM + "".join(
        f"\n{name}:\n    .byte {', '.join(str(c) for c in data)}\n" for name, data in STRINGS
    )
    blob = bytes(ks.asm(src, CAVE)[0])
    head = ASM.split("hook_connect:")[0]
    n_ins = sum(1 for l in head.splitlines() if l.strip() and not l.strip().endswith(":"))
    hook_con = CAVE + 4 * n_ins
    b_gai = bytes(ks.asm(f"b {CAVE:#x}", PLT_GETADDRINFO)[0])
    b_con = bytes(ks.asm(f"b {hook_con:#x}", PLT_CONNECT)[0])
    return {CAVE: blob, PLT_GETADDRINFO: b_gai, PLT_CONNECT: b_con}


# Pre-assembled output of assemble() (regenerate with: python scripts/net_hooks.py)
NET_HOOK_PATCHES = {
    0xe0a080: bytes.fromhex("a00200b4e90300aa2a154038eaffff35290100cb290500d13f1d00f1c30100540a00098b4a1d00d10b0600100c0080d24d696c38ad011b326e696c38bf010e6ba10000548c0500919f1d00f121ffff5400050010f0b400b0113e42f920021fd6e10300b4290040793f09007181030054290440b9ea0f80520a20a0723f010a6be1020054290440790b008a523f010b6ba00000542b6097523f010b6b800000540f000014cc089452020000140c698152fd7bbea9fd030091292840a9e92b01a9ec270079e1430091f0b400b011be41f920023fd6fd7bc2a8c0035fd6f0b400b011be41f920021fd67562692e636f6d003132372e302e302e3100"),
    0xc6eb80: bytes.fromhex("406d0614"),
    0xc6e980: bytes.fromhex("d86d0614"),
}

if __name__ == "__main__":
    import capstone
    patches = assemble()
    md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)
    for addr, b in patches.items():
        print(f"    {addr:#x}: bytes.fromhex(\"{b.hex()}\"),")
    for addr, b in patches.items():
        print(f"\n; {addr:#x} ({len(b)} bytes)")
        for ins in md.disasm(b, addr):
            print(f"  {ins.address:#x}: {ins.mnemonic} {ins.op_str}")
