#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
网易云 LRC 歌词修复工具

网易云导出的 .lrc 文件开头混有 JSON 逐字歌词数据:
  {"t":0,"c":[{"tx":"作词: "},{"tx":"xxx",...}]}
  {"t":1000,"c":[...]}
  [00:10.356]歌词行
MusicBee 等播放器无法解析 JSON 行, 导致歌词不渲染。

本工具: 把 JSON 行转成标准 LRC 时间行, 并统一时间戳为 [mm:ss.xx]

用法: python FixNcmLrc.py <lrc文件或目录>
"""
import os, sys, re, json, glob

TIME_RE = re.compile(r"^\[(\d+):(\d+)(?:\.(\d{1,3}))?\]")

def fmt_ms(ms):
    sign = "-" if ms < 0 else ""
    ms = abs(int(ms))
    m, rem = divmod(ms, 60000)
    s, cs = divmod(rem, 1000)
    return "[%s%02d:%02d.%02d]" % (sign, m, s, cs // 10)

def fix_line(line):
    s = line.strip()
    if not s:
        return None
    if s.startswith("{"):  # JSON 逐字行 {"t":ms,"c":[{"tx":...}]}
        try:
            obj = json.loads(s)
            t = obj.get("t", 0)
            txt = "".join(p.get("tx", "") for p in obj.get("c", []) if isinstance(p, dict))
            return fmt_ms(t) + txt
        except Exception:
            return None
    m = TIME_RE.match(s)
    if m:  # 标准 LRC 行, 规范化时间戳
        minute, sec = int(m.group(1)), int(m.group(2))
        centi = int((m.group(3) or "0").ljust(2, "0")[:2])
        return "[%02d:%02d.%02d]%s" % (minute, sec, centi, s[m.end():])
    return s

def fix_file(path):
    text = open(path, encoding="utf-8-sig").read()
    out = []
    for raw in text.splitlines():
        fixed = fix_line(raw)
        if fixed is not None:
            out.append(fixed)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")

def main():
    if len(sys.argv) < 2:
        sys.exit("用法: python FixNcmLrc.py <lrc文件或目录>")
    path = sys.argv[1]
    targets = sorted(glob.glob(os.path.join(path, "*.lrc"))) if os.path.isdir(path) else [path]
    for t in targets:
        try:
            fix_file(t)
            print("[OK] %s" % os.path.basename(t))
        except Exception as e:
            print("[FAIL] %s : %s" % (os.path.basename(t), e))

if __name__ == "__main__":
    main()
