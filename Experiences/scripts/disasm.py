#!/usr/bin/env python3
"""
DLL 反汇编辅助脚本 (pefile + capstone)

用法:
  python disasm.py <dll> <rva_hex> <字节数> [--arch 32|64]
  python disasm.py QQMusicCommon.dll 0x12F0B 0x300

示例:
  python disasm.py E:\\QQMusic\\QQMusicCommon.dll 0x12FB5 0x200   # Open
  python disasm.py E:\\QQMusic\\CommonFunction.dll 0x9B40 0x160   # PRGA
"""
import sys
import pefile
import capstone


def disasm(path, rva, size, arch=32):
    pe = pefile.PE(path)
    base = pe.OPTIONAL_HEADER.ImageBase
    md = capstone.Cs(
        capstone.CS_ARCH_X86, capstone.CS_MODE_32 if arch == 32 else capstone.CS_MODE_64
    )
    code = pe.get_data(rva, size)
    print(f"=== {path} RVA=0x{rva:X} ({size} bytes) ===")
    for ins in md.disasm(code, base + rva):
        print(f"0x{ins.address - base:08X}: {ins.mnemonic} {ins.op_str}")


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print(__doc__)
        sys.exit(1)
    path = sys.argv[1]
    rva = int(sys.argv[2], 16)
    size = int(sys.argv[3], 16)
    arch = 32
    if "--arch" in sys.argv:
        arch = int(sys.argv[sys.argv.index("--arch") + 1])
    disasm(path, rva, size, arch)
