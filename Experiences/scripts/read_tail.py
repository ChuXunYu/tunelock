#!/usr/bin/env python3
"""
mflac 文件头/尾结构分析脚本

功能:
  1. 打印文件头部字节（ASCII + hex）
  2. 检测尾部 musicex 标记、UTF-16LE 文件名、歌曲 ID
  3. 对比 musics 文件与缓存文件（找 192 字节差异）
  4. 计算熵、base64 字符占比

用法:
  python read_tail.py <file.mflac> [<cache_file>]

示例:
  python read_tail.py musics\\Billie.mflac "D:\\Temp\\QQ_music_caches\\...\\xxx.mflac"
"""
import sys
import pathlib
import string
import math
import collections

B64 = set((string.ascii_letters + string.digits + "+/").encode())


def entropy(chunk):
    cnt = collections.Counter(chunk)
    n = len(chunk)
    return -sum((c / n) * math.log2(c / n) for c in cnt.values())


def analyze(path, cache_path=None):
    b = pathlib.Path(path).read_bytes()
    print(f"=== {pathlib.Path(path).name} size={len(b)} ===")
    print("head64:", b[:64].hex(" "))
    print("head ascii:", "".join(chr(c) if 32 <= c < 127 else "." for c in b[:64]))

    # base64 占比
    n = sum(1 for c in b[:128] if c in B64)
    print(f"head128 base64 占比: {n}/128")

    # 熵
    for off in [0, 1024, len(b) // 2, len(b) - 4096]:
        print(f"entropy@{off}: {entropy(b[off:off + 4096]):.3f}")

    # 尾部结构
    off = b.rfind(b"musicex")
    print("musicex @", off)
    if off > 0:
        print("tail before musicex:", b[off - 32:off].hex(" "))
    print("tail32:", b[-32:].hex(" "))

    # UTF-16LE 字符串
    import re
    for m in re.finditer(rb"(?:[\x20-\x7e]\x00){4,}", b[-512:]):
        print("UTF16:", m.group().decode("utf-16le"))

    # 与缓存文件对比
    if cache_path:
        c = pathlib.Path(cache_path).read_bytes()
        print(f"\n缓存文件 size={len(c)} 差={len(b) - len(c)}")
        print("musics.startswith(cache):", b[: len(c)] == c)
        if len(b) > len(c):
            extra = b[len(c):]
            print("尾部附加块 len:", len(extra))
            print("附加块 hex:", extra.hex(" "))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    cache = sys.argv[2] if len(sys.argv) > 2 else None
    analyze(sys.argv[1], cache)
