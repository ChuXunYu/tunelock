#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
QQ 音乐歌单导出工具 (通过公开歌单 API, 无需登录)

用法: python tools/playlist_export.py <歌单链接或ID> [输出文件]
示例: python tools/playlist_export.py https://y.qq.com/n/ryqq/playlist?id=1234567 out.txt

输出: 默认在 ./歌单名.txt (每行 "歌手 - 歌名", 保持歌单顺序)
      + 同名 .m3u8 播放列表
"""
import sys, os, re, json, urllib.request, urllib.parse

API = "https://c.y.qq.com/qzone/fcg-bin/fcg_ucc_getcdinfo_byids_cp.fcg"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
    "Referer": "https://y.qq.com/",
}

def extract_id(text):
    m = re.search(r"[?&]id=(\d+)", text)
    if m:
        return m.group(1)
    m = re.search(r"\b(\d{6,})\b", text)
    if m:
        return m.group(1)
    return text.strip()

def fetch_playlist(dissid):
    qs = urllib.parse.urlencode({
        "type": 1, "json": 1, "utf8": 1, "onlysong": 0,
        "disstid": dissid, "format": "json", "g_tk": 5381,
    })
    req = urllib.request.Request(API + "?" + qs, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))

def main():
    if len(sys.argv) < 2:
        sys.exit("用法: python tools/playlist_export.py <歌单链接或ID> [输出文件]")
    dissid = extract_id(sys.argv[1])
    out = sys.argv[2] if len(sys.argv) > 2 else None

    data = fetch_playlist(dissid)
    cd = data.get("cdlist") or []
    if not cd or not cd[0].get("songlist"):
        print("未获取到歌单 (ID=%s), 响应: %s" % (dissid, str(data)[:200]))
        return
    pl = cd[0]
    name = pl.get("dissname") or "playlist_" + dissid
    songs = pl.get("songlist", [])
    lines = []
    for s in songs:
        singers = "/".join(x.get("name", "") for x in s.get("singer", []))
        lines.append((singers + " - " + s.get("songname", "")).strip(" -"))

    out = out or name + ".txt"
    with open(out, "w", encoding="utf-8") as f:
        f.write("歌单: %s (ID %s)\n" % (name, dissid))
        f.write("共 %d 首\n\n" % len(lines))
        for i, l in enumerate(lines, 1):
            f.write("%03d. %s\n" % (i, l))
    m3u = os.path.splitext(out)[0] + ".m3u8"
    with open(m3u, "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n")
        for l in lines:
            f.write("#EXTINF:-1,%s\n" % l)
            f.write("\n")
    print("歌单: %s (%d 首)" % (name, len(songs)))
    print("已导出: %s" % out)
    print("已导出: %s" % m3u)

if __name__ == "__main__":
    main()
