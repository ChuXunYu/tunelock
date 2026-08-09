#!/usr/bin/env python3
r"""
DLL 导出符号 / 字符串 扫描辅助脚本

用法:
  python scan_dll.py <dll> --export [--filter KEYWORD]
  python scan_dll.py <dll> --string KEYWORD [--utf16]
  python scan_dll.py <目录> --export --filter EncAndDesMediaFile   # 扫目录

示例:
  python scan_dll.py E:\QQMusic\QQMusicCommon.dll --export --filter EncAndDesMediaFile
  python scan_dll.py E:\QQMusic --string musicex
"""
import sys
import pathlib
import re


def scan_exports(path, kw=None):
    import pefile

    pe = pefile.PE(path)
    pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_EXPORT"]])
    if not hasattr(pe, "DIRECTORY_ENTRY_EXPORT"):
        print(f"({path.name}) no exports")
        return
    for exp in pe.DIRECTORY_ENTRY_EXPORT.symbols:
        n = exp.name.decode("latin1", "replace") if exp.name else ""
        if kw and kw.lower() not in n.lower():
            continue
        print(f"0x{exp.address:08X}  ord={exp.ordinal}  {n}")


def scan_strings(path, kw, utf16=False):
    data = pathlib.Path(path).read_bytes()
    pat = (kw.encode("utf-16le") if utf16 else kw.encode())
    for m in re.finditer(re.escape(pat), data):
        i = m.start()
        # 打印上下文
        s = data[max(0, i - 60): i + 80]
        s = re.sub(rb"[^\x20-\x7e]", b".", s)
        print(f"@0x{i:X}: {s.decode('latin1')}")


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        sys.exit(1)

    target = args[0]
    mode = args[1] if len(args) > 1 else "--export"

    if "--string" in args:
        idx = args.index("--string")
        kw = args[idx + 1]
        utf16 = "--utf16" in args
        if pathlib.Path(target).is_dir():
            for f in pathlib.Path(target).iterdir():
                if f.suffix.lower() in (".dll", ".exe"):
                    try:
                        needle = kw.encode("utf-16le") if utf16 else kw.encode()
                        if needle in f.read_bytes():
                            print(f"=== {f.name} ===")
                            scan_strings(str(f), kw, utf16)
                    except Exception:
                        pass
        else:
            scan_strings(target, kw, utf16)
    else:
        kw = None
        if "--filter" in args:
            kw = args[args.index("--filter") + 1]
        if pathlib.Path(target).is_dir():
            for f in pathlib.Path(target).iterdir():
                if f.suffix.lower() in (".dll", ".exe"):
                    print(f"=== {f.name} ===")
                    scan_exports(str(f), kw)
        else:
            scan_exports(target, kw)
