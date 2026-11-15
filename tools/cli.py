#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""统一命令行：无界面批量解密 / 体检。

用法::

    python -m tools decrypt <文件或目录...> [-o 输出目录] [-r] [--only qq|kugou|netease]
    python -m tools info    <文件或目录...> [-r]
    python -m tools --version

示例::

    python -m tools info  samples                 # 先看能不能解、走哪条路径
    python -m tools decrypt samples -o decoded -r # 批量解密（自动分平台）

QQ 音乐需要先编译 QqmDec.exe（见 build/），酷狗需要本机数据库有 eKey。
"""
import argparse
import os
import sys

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
PKG_ROOT = os.path.dirname(TOOLS_DIR)
for _p in (PKG_ROOT, TOOLS_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

try:
    from tools import __version__ as VERSION
except Exception:  # 单文件方式运行时兜底
    VERSION = "0.0.0"

import decrypt  # noqa: E402
from decrypt import (  # noqa: E402
    DEC_OK,
    IMPORT_ERR,
    collect_tasks,
    is_supported,
    platform_of,
    py_decrypt,
    qq_hint,
    qq_output_ext,
    qq_ready,
    resolve_output,
)

PLATFORM_LABEL = {"qq": "QQ音乐", "kugou": "酷狗", "netease": "网易云"}
EXIT_OK = 0
EXIT_FAIL = 1
EXIT_USAGE = 2


def _force_utf8_stdout():
    """Windows 控制台默认 GBK，中文会乱码；这里统一按 UTF-8 输出。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _iter_files(paths, recursive):
    """展开为文件列表（不过滤扩展名，交给调用方判断）。"""
    out = []
    for p in paths:
        if os.path.isdir(p):
            if recursive:
                for dp, _dn, fns in os.walk(p):
                    out.extend(os.path.join(dp, fn) for fn in sorted(fns))
            else:
                out.extend(os.path.join(p, fn) for fn in sorted(os.listdir(p)))
        elif os.path.isfile(p):
            out.append(p)
    return out


def cmd_info(args):
    files = _iter_files(args.paths, args.recursive)
    if not files:
        print("没有找到文件")
        return EXIT_USAGE
    supported = [f for f in files if is_supported(f)]
    print("依赖: %s" % ("OK" if DEC_OK else "缺失 -> %s" % IMPORT_ERR))
    if qq_ready():
        print("QQ 音乐路径: 可用（exe + 两个 DLL 齐备）")
    else:
        print("QQ 音乐路径: 不可用 -> %s" % qq_hint())
    print("扫描 %d 个文件，其中 %d 个是可解密的加密封装\n" % (len(files), len(supported)))
    for f in supported:
        plat = platform_of(f)
        note = ""
        if plat == "kugou" and DEC_OK:
            note = "  (需本机数据库 eKey)"
        elif plat == "qq" and not qq_ready():
            note = "  (QQ 解密链未就绪)"
        size = os.path.getsize(f)
        print("  %-8s %8.1f MB  %s%s" % (PLATFORM_LABEL[plat], size / 1048576, f, note))
    if len(supported) != len(files):
        print("\n另有 %d 个文件不在支持列表（%s）"
              % (len(files) - len(supported), " ".join(decrypt.TARGET_EXTS)))
    return EXIT_OK


def cmd_decrypt(args):
    if not DEC_OK and args.only != "qq":
        print("依赖缺失：%s（pip install -r requirements.txt）" % IMPORT_ERR)
        return EXIT_USAGE

    tasks = collect_tasks(args.paths, recursive=args.recursive)
    if args.only:
        tasks = [t for t in tasks if platform_of(t[0]) == args.only]
    if not tasks:
        print("没有可处理的文件（支持 %s）" % " ".join(decrypt.TARGET_EXTS))
        return EXIT_USAGE

    out_root = os.path.abspath(args.out) if args.out else None
    if out_root:
        os.makedirs(out_root, exist_ok=True)

    single = len(tasks) == 1
    ok = 0
    failed = []
    for src, rel, droot in tasks:
        d, base = resolve_output(src, rel, droot, out_root, None, single)
        os.makedirs(d, exist_ok=True)
        plat = platform_of(src)
        try:
            if plat == "qq":
                out = os.path.join(d, base + qq_output_ext(src))
                done, msg = decrypt.qq_decrypt(src, out)
                if not done:
                    raise decrypt.DecryptError(msg)
                info = ""
            else:
                data, ext, info = py_decrypt(src)
                out = os.path.join(d, base + "." + ext)
                with open(out, "wb") as f:
                    f.write(data)
            ok += 1
            print("[成功] %s -> %s%s" % (os.path.basename(src), out,
                                       "  " + info if info else ""))
        except Exception as exc:
            failed.append((src, str(exc)))
            print("[失败] %s : %s" % (os.path.basename(src), exc))

    print("\n完成: %d/%d 成功" % (ok, len(tasks)))
    if failed:
        print("失败清单:")
        for src, why in failed:
            print("  - %s : %s" % (src, why))
        return EXIT_FAIL
    return EXIT_OK


def build_parser():
    ap = argparse.ArgumentParser(
        prog="tunelock",
        description="TuneLock：QQ音乐 / 酷狗 / 网易云 加密封装音频解密",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("--version", action="version", version="%(prog)s " + VERSION)
    sub = ap.add_subparsers(dest="command")

    p_dec = sub.add_parser("decrypt", help="批量解密")
    p_dec.add_argument("paths", nargs="+", help="文件或目录")
    p_dec.add_argument("-o", "--out", help="输出根目录（默认与输入同级 / 输入名_decoded）")
    p_dec.add_argument("-r", "--recursive", action="store_true", help="目录输入时递归子目录")
    p_dec.add_argument("--only", choices=["qq", "kugou", "netease"], help="只处理某个平台")

    p_info = sub.add_parser("info", help="扫描文件，显示平台与可解性")
    p_info.add_argument("paths", nargs="+", help="文件或目录")
    p_info.add_argument("-r", "--recursive", action="store_true", help="目录输入时递归子目录")
    return ap


def main(argv=None):
    _force_utf8_stdout()
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return EXIT_USAGE
    return cmd_decrypt(args) if args.command == "decrypt" else cmd_info(args)


if __name__ == "__main__":
    sys.exit(main())
