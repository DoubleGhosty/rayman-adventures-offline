"""Optional DEBUG instrumentation for libuaf.so (never applied to release builds).

    python scripts/build_libuaf_offline.py --debug

1. Function-entry hooks (tag "RaymanDbg"): the first instruction of a function is replaced
   by a branch into a code cave that logs some arguments with __android_log_print, replays
   the displaced instruction and jumps back. The library load base is printed ("base=") so
   vtables can be mapped back to symbols (vtable symbol = vt - base - 0x10).
2. ITF engine logger (tag "RaymanITF"): ITF::Logger::print / printV are empty stubs in the
   release build; they are rewired to __android_log_print / __android_log_vprint, which
   exposes all of the engine's own diagnostics ("url=%s", "Request failed: %s"...).

Read with:  adb logcat -s RaymanDbg RaymanITF
"""

CAVE = 0xE0A200            # after the network hooks (0xe0a080..0xe0a17a), same zero run
CAVE_END = 0xE0AC00        # egg_pick_hooks.py uses 0xe0ac00.., incubator_hooks.py 0xe0af00..
LOG_PRINT_PLT = 0xC6E930   # __android_log_print@plt
LOG_VPRINT_PLT = 0xC6F9B0  # __android_log_vprint@plt
LOGGER_PRINT = 0x18A9A24   # ITF::Logger::print(this, fmt, ...)      empty stub, 0x44 bytes
LOGGER_PRINTV = 0x18A9A68  # ITF::Logger::printV(this, fmt, va_list) single "ret"

# (address, displaced instruction (position independent), format, argument setup)
# The setup runs with the original x0..x8 live and must put printf arguments in x3, x4, x5, x7
# (x0..x2 = prio/tag/fmt, x6 = load base, always the 4th printf argument).
HOOKS = [
    (0x1827CAC, "sub sp, sp, #0x50",
     "Module::setState this=%p vt=%p state=%d base=%p lr=%p",
     "mov x3, x0\n    ldr x4, [x0]\n    mov w5, w1\n    mov x7, x30"),
    (0x1827FA8, "ldr w2, [x0, #0x2bc]",
     "Module::setIsDisconnecting this=%p vt=%p err0=%08x base=%p err1=%08x",
     "mov x3, x0\n    ldr x4, [x0]\n    ldr w5, [x1]\n    ldr w7, [x1, #4]"),
    # Module::disconnect (vtable +0x28): state 4 -> 3 without an error, as in the title-screen
    # login loop (UbiServicesModule_SDK connected then disconnected 1 ms later); lr = the caller
    (0x1827F88, "ldr w2, [x0, #0x2bc]",
     "Module::disconnect this=%p vt=%p state=%d base=%p lr=%p",
     "mov x3, x0\n    ldr x4, [x0]\n    ldr w5, [x0, #0x2bc]\n    mov x7, x30"),
    # inventory: an elixir gain and the store credit it turns into (no credit = no stock found)
    (0x1785540, "sub sp, sp, #0x40",
     "InventoryManager::addElixirs type=%d amount=%d acq=%d base=%p",
     "mov w5, w3\n    mov w3, w1\n    mov w4, w2"),
    (0x1840cc0, "sub sp, sp, #0xb0",
     "dynamicStore::creditItem id=%d amount=%d this=%p base=%p",
     "mov w3, w1\n    mov w4, w2\n    mov x5, x0"),
    # creature picks (adventure eggs, ticket / magnifying glass / Charlie eggs via the hooks)
    (0x16922cc, "sub sp, sp, #0xa0",
     "CreatureManager::HatchSimulation acq=%d family=%d rarity=%d base=%p forceNew=%d",
     "mov w5, w3\n    mov w3, w1\n    mov w7, w4\n    mov w4, w2"),
    # creature ids picked by egg_pick_hooks.py (after their cave)
    (0x1687968, "mov w2, #2",
     "  Charlie egg: charlie=%d creature=%u x=%d base=%p",
     "mov w3, w0\n    mov w4, w1\n    mov w5, #0"),
    (0x16e3b80, "str x5, [sp, #0x60]",
     "  Magnifying glass egg: creature=%u i=%d x=%d base=%p",
     "mov w3, w1\n    mov w4, w19\n    mov w5, #0"),
    # A hook in the middle of a function can read the caller's stack: this frame adds 0x60
    # (e.g. inside createInventoryItemsIfNeeded at 0x1842068, "ldr w3, [sp, #0xd4]" = its sp+0x74).
]


def _bytes_directive(data):
    return "    .byte " + ", ".join(str(c) for c in data) + "\n"


def _hook_asm(i, addr, displaced, setup):
    return f"""
dbg_hook_{i}:
    stp x29, x30, [sp, #-0x60]!
    stp x0, x1, [sp, #0x10]
    stp x2, x3, [sp, #0x20]
    stp x4, x5, [sp, #0x30]
    stp x6, x7, [sp, #0x40]
    str x8, [sp, #0x50]
    mov x29, sp
    {setup}
    adr x6, dbg_hook_0
    sub x6, x6, #{CAVE & 0xfff:#x}
    sub x6, x6, #{CAVE >> 12:#x}, lsl #12
    mov w0, #4
    adr x1, dbg_tag
    adr x2, dbg_fmt_{i}
    bl {LOG_PRINT_PLT:#x}
    ldp x0, x1, [sp, #0x10]
    ldp x2, x3, [sp, #0x20]
    ldp x4, x5, [sp, #0x30]
    ldp x6, x7, [sp, #0x40]
    ldr x8, [sp, #0x50]
    ldp x29, x30, [sp], #0x60
    {displaced}
    b {addr + 4:#x}
"""


def _source():
    code = "".join(_hook_asm(i, a, d, s) for i, (a, d, _f, s) in enumerate(HOOKS))
    code += f"""
dbg_printv:
    mov x3, x2
    mov x2, x1
    adr x1, dbg_itf_tag
    mov w0, #4
    b {LOG_VPRINT_PLT:#x}
"""
    data = "\ndbg_tag:\n" + _bytes_directive(b"RaymanDbg\x00")
    data += "dbg_itf_tag:\n" + _bytes_directive(b"RaymanITF\x00")
    for i, (_a, _d, fmt, _s) in enumerate(HOOKS):
        data += f"dbg_fmt_{i}:\n" + _bytes_directive(fmt.encode() + b"\x00")
    return code, data


def _label_addr(ks, code, label):
    """Address of a label located in the code part (only 4-byte instructions before it)."""
    prefix = code.split(label + ":")[0]
    n = sum(1 for l in prefix.splitlines() if l.strip() and not l.strip().endswith(":"))
    return CAVE + 4 * n


def assemble():
    import keystone
    ks = keystone.Ks(keystone.KS_ARCH_ARM64, keystone.KS_MODE_LITTLE_ENDIAN)
    code, data = _source()
    blob = bytes(ks.asm(code + data, CAVE)[0])
    assert CAVE + len(blob) <= CAVE_END, "debug cave overflow"
    patches = {CAVE: blob}
    for i, (addr, *_rest) in enumerate(HOOKS):
        entry = _label_addr(ks, code, f"dbg_hook_{i}")
        patches[addr] = bytes(ks.asm(f"b {entry:#x}", addr)[0])
    printv = _label_addr(ks, code, "dbg_printv")
    patches[LOGGER_PRINTV] = bytes(ks.asm(f"b {printv:#x}", LOGGER_PRINTV)[0])
    # address of dbg_itf_tag = code size + size of the dbg_tag bytes (10)
    tag = _label_addr(ks, code + "\nend_of_code:", "end_of_code") + len(b"RaymanDbg\x00")
    assert blob[tag - CAVE:tag - CAVE + 10] == b"RaymanITF\x00"
    # ITF::Logger::print body: (this, fmt, a0..a4) -> __android_log_print(4, tag, fmt, a0..a4)
    patches[LOGGER_PRINT] = bytes(ks.asm(f"""
        mov x7, x6
        mov x6, x5
        mov x5, x4
        mov x4, x3
        mov x3, x2
        mov x2, x1
        adrp x1, {tag & ~0xfff:#x}
        add x1, x1, #{tag & 0xfff:#x}
        mov w0, #4
        b {LOG_PRINT_PLT:#x}
    """, LOGGER_PRINT)[0])
    assert len(patches[LOGGER_PRINT]) <= 0x44
    return patches


if __name__ == "__main__":
    import capstone
    md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)
    for a, b in assemble().items():
        print(f"; {a:#x} ({len(b)} bytes)")
        for ins in md.disasm(b, a):
            print(f"  {ins.address:#x}: {ins.mnemonic} {ins.op_str}")
