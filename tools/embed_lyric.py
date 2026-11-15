#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
歌词内嵌工具: 把同名 .lrc 写入音频文件 (MP3/FLAC/OGG), 无损重封装

原理: ffmpeg -c copy -metadata lyrics=<lrc内容> 重新封装,
      音频流原样复制(无损), 歌词写入容器标签:
      - MP3  -> ID3v2 USLT 帧
      - FLAC -> VORBIS_COMMENT LYRICS 字段
      - OGG  -> Vorbis LYRICS 注释
      MusicBee / foobar2000 等直接读取内嵌歌词, 无需旁挂 .lrc

用法: python tools/embed_lyric.py <音频文件或目录>
依赖: ffmpeg（PATH 里能找到即可；也可用环境变量 FFMPEG 指定绝对路径）
"""
import os, sys, glob, shutil, subprocess

AUDIO_EXTS = (".mp3", ".flac", ".ogg", ".m4a", ".wav", ".aac", ".opus")

def find_ffmpeg():
    """查找 ffmpeg：环境变量 FFMPEG → PATH → 常见包管理器安装位置。"""
    env = os.environ.get("FFMPEG")
    if env and os.path.isfile(env):
        return env
    found = shutil.which("ffmpeg")
    if found:
        return found
    for cand in (r"D:\Scoop\apps\ffmpeg\current\bin\ffmpeg.exe",
                 os.path.expanduser(r"~\scoop\apps\ffmpeg\current\bin\ffmpeg.exe"),
                 r"C:\ProgramData\chocolatey\bin\ffmpeg.exe"):
        if os.path.isfile(cand):
            return cand
    return None

def embed_one(audio):
    base = os.path.splitext(audio)[0]
    lrc = base + ".lrc"
    if not os.path.exists(lrc):
        return False, "无同名 .lrc"
    with open(lrc, encoding="utf-8-sig") as f:
        lyric = f.read()
    ff = find_ffmpeg()
    if not ff:
        return False, "未找到 ffmpeg"
    tmp = os.path.splitext(audio)[0] + ".embed" + os.path.splitext(audio)[1]
    try:
        r = subprocess.run(
            [ff, "-y", "-i", audio, "-map", "0:a", "-c", "copy",
             "-metadata", "lyrics=" + lyric, tmp],
            capture_output=True, timeout=600)
        if r.returncode != 0:
            return False, r.stderr.decode("utf-8", "replace")[-200:]
        os.replace(tmp, audio)
        return True, "已内嵌歌词 (%d 字符)" % len(lyric)
    except Exception as e:
        try:
            if os.path.exists(tmp): os.remove(tmp)
        except Exception:
            pass
        return False, str(e)

def main():
    if len(sys.argv) < 2:
        sys.exit("用法: python tools/embed_lyric.py <音频文件或目录>")
    path = sys.argv[1]
    if os.path.isdir(path):
        targets = []
        for e in AUDIO_EXTS:
            targets += glob.glob(os.path.join(path, "*" + e))
        targets.sort()
    else:
        targets = [path]
    ok = 0
    for t in targets:
        okk, msg = embed_one(t)
        if okk:
            print("[成功] %s -> %s" % (os.path.basename(t), msg))
            ok += 1
        else:
            print("[跳过] %s : %s" % (os.path.basename(t), msg))
    print("\n完成: %d/%d 已内嵌" % (ok, len(targets)))

if __name__ == "__main__":
    main()
