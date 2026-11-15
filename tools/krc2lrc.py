#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
酷狗 KRC 加密歌词解密工具 (.krc -> .lrc)

原理:
  1. 文件头 4 字节 magic "krc1"
  2. 从偏移 4 起, 每字节 XOR 固定 16 字节 key
  3. zlib 解压 -> KRC 内部文本 (逐字对轨格式: [行start,行长]<字start,字长,0>字...)
  4. 转成标准 LRC ([mm:ss.xx] 行)

用法:
  python tools/krc2lrc.py <输入krc文件或目录> [输出目录]
  # 默认输入 D:\\KuGou\\Lyric (酷狗歌词缓存目录), 默认输出 ./lyrics_krc

说明:
  输出 lrc 文件名 = krc 去掉尾部 "-<hash>-<id>-00000000" 后缀
  (如 "歌手 - 歌名-<hash>-<id>-00000000.krc" -> "歌手 - 歌名.lrc"),
  便于与同名解密音频配对。
"""
import os, sys, re, zlib, glob, argparse

KRC_KEY = bytes([
    0x40, 0x47, 0x61, 0x77, 0x5E, 0x32, 0x74, 0x47,
    0x51, 0x36, 0x31, 0x2D, 0xCE, 0xD2, 0x6E, 0x69,
])
KEEP_TAGS = ("ar", "ti", "al", "offset")

def decrypt_krc(data):
    """krc 字节 -> KRC 内部文本"""
    if data[:4] != b"krc1":
        raise ValueError("不是 krc 文件 (magic 应为 krc1)")
    buf = bytearray(data[4:])
    for i in range(len(buf)):
        buf[i] ^= KRC_KEY[i % 16]
    return zlib.decompress(bytes(buf)).decode("utf-8", "replace")

def fmt_time(ms):
    sign = "-" if ms < 0 else ""
    ms = abs(ms)
    m, rem = divmod(ms, 60000)
    s, cs = divmod(rem, 1000)
    return "[%s%02d:%02d.%02d]" % (sign, m, s, cs // 10)

def krc_to_lrc(text):
    """KRC 内部文本 -> 标准 LRC 文本"""
    lines = []
    offset = 0
    mo = re.search(r"\[offset:(-?\d+)\]", text)
    if mo:
        offset = int(mo.group(1))
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("[") and "<" not in line:
            m = re.match(r"^\[([^:]+):", line)
            if m and m.group(1) in KEEP_TAGS:
                lines.append(line)
            continue
        m = re.match(r"^\[(\d+),(\d+)\](.*)$", line)
        if not m:
            continue
        line_start = int(m.group(1))
        content = m.group(3)
        parts = re.findall(r"<(\d+),(\d+),\d+>([^<]*)", content)
        if not parts:
            continue
        words = "".join(p[2] for p in parts)
        t = line_start + int(parts[0][0]) + offset
        lines.append(fmt_time(t) + words)
    return "\n".join(lines) + "\n"

def clean_name(name):
    """'歌手 - 歌名-<hash>-<id>-00000000.krc' -> '歌手 - 歌名.lrc'"""
    parts = name.split("-")
    if len(parts) >= 4:
        tail = parts[-3:]
        if (re.fullmatch(r"[0-9A-Fa-f]{32}", tail[0]) and
                re.fullmatch(r"[0-9A-Fa-f]+", tail[1]) and
                re.fullmatch(r"[0-9A-Fa-f]+\.krc$", tail[2], re.I)):
            return "-".join(parts[:-3]) + ".lrc"
    return os.path.splitext(name)[0] + ".lrc"

def convert_one(src, outdir):
    with open(src, "rb") as f:
        data = f.read()
    text = decrypt_krc(data)
    lrc = krc_to_lrc(text)
    out = os.path.join(outdir, clean_name(os.path.basename(src)))
    with open(out, "w", encoding="utf-8") as f:
        f.write(lrc)
    return out

def default_krc_dir():
    """酷狗歌词缓存目录：环境变量 KUGOU_LYRIC_DIR → D:\\KuGou\\Lyric（存在才用）。"""
    env = os.environ.get("KUGOU_LYRIC_DIR")
    if env and os.path.isdir(env):
        return env
    legacy = r"D:\KuGou\Lyric"
    return legacy if os.path.isdir(legacy) else "."

def main():
    ap = argparse.ArgumentParser(description="酷狗 KRC 加密歌词解密 (.krc -> .lrc)")
    ap.add_argument("path", nargs="?", default=default_krc_dir(),
                    help="krc 文件或目录 (默认 KUGOU_LYRIC_DIR，其次 D:\\KuGou\\Lyric)")
    ap.add_argument("outdir", nargs="?", default="lyrics_krc", help="输出目录 (默认 ./lyrics_krc)")
    args = ap.parse_args()

    if os.path.isdir(args.path):
        targets = sorted(glob.glob(os.path.join(args.path, "*.krc")))
    else:
        targets = [args.path] if args.path.lower().endswith(".krc") else []
    if not targets:
        print("未找到 .krc 文件")
        return
    os.makedirs(args.outdir, exist_ok=True)
    ok = 0
    for t in targets:
        try:
            out = convert_one(t, args.outdir)
            print("[成功] %s -> %s" % (os.path.basename(t), os.path.basename(out)))
            ok += 1
        except Exception as e:
            print("[失败] %s : %s" % (os.path.basename(t), e))
    print("\n完成: %d/%d" % (ok, len(targets)))

if __name__ == "__main__":
    main()
