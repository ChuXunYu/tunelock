#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
酷狗 kgg 解密工具 —— 推荐路径：直接调 QMDECRYPTION.dll

关键修正 (2026-08-10):
  ``CreateDecryption`` 必须传入数据库 eKey 的 **base64 原文**（字符串），
  DLL 内部自行 base64 解码 + TEA 派生 + 构建解密器。
  传派生后的二进制 key 会输出乱码。

用法:
  python tools/kugou_dll.py <kgg文件或目录> [输出目录] [--dll DLL] [--db DB]

依赖:
  - cryptography：解密 KGMusicV3.db 查 eKey
  - QMDECRYPTION.dll：随酷狗安装（x64），首次使用用 ``--dll`` 指一次，
    或用环境变量 ``KG_DLL`` 固定，程序也会自动扫描常见安装目录

说明: 数据库解密、eKey 派生等公共逻辑复用 kugou.py（纯 Python 路径），
      本文件只保留 DLL 调用部分，避免两份实现漂移。
"""
import sys, os, ctypes, argparse

try:
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes  # noqa: F401
    from cryptography.hazmat.primitives import hashes  # noqa: F401
except ImportError:
    sys.exit("缺少依赖 cryptography，请先执行: pip install cryptography")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kugou import find_db, load_ekey_map, iter_targets  # noqa: E402

KGM_MAGIC = bytes([0x7C, 0xD5, 0x32, 0xEB, 0x86, 0x02, 0x7F, 0x4B,
                   0xA8, 0xAF, 0xA6, 0x8E, 0x0F, 0xFF, 0x99, 0x14])
DLL_NAME = "QMDECRYPTION.dll"


# ---------- DLL 定位 ----------
def find_dll():
    """按 环境变量 KG_DLL → 常见酷狗安装目录 的顺序找 QMDECRYPTION.dll。"""
    env = os.environ.get("KG_DLL")
    if env and os.path.isfile(env):
        return env
    roots = []
    for drive in ("E:\\", "D:\\", "C:\\"):
        roots.append(os.path.join(drive, "KGMusic"))
    for var in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
        base = os.environ.get(var, "")
        if base:
            roots.append(os.path.join(base, "KGMusic"))
            roots.append(os.path.join(base, "KuGou"))
    for root in roots:
        if not os.path.isdir(root):
            continue
        # 酷狗按版本号建子目录：KGMusic\\20.1.41.27870\\QMDECRYPTION.dll
        direct = os.path.join(root, DLL_NAME)
        if os.path.isfile(direct):
            return direct
        for dp, _dn, fns in os.walk(root):
            if DLL_NAME in fns:
                return os.path.join(dp, DLL_NAME)
    return None


# ---------- DLL 解密 ----------
class Qmdll:
    def __init__(self, path):
        self.dll = ctypes.CDLL(path)
        self.Create = self.dll.CreateDecryption
        self.Create.argtypes = [ctypes.c_void_p, ctypes.c_int]
        self.Create.restype = ctypes.c_void_p
        self.Decrypt = self.dll.Decrypt
        self.Decrypt.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_int]
        self.Decrypt.restype = ctypes.c_int
        self.Destroy = self.dll.DestroyDecryption
        self.Destroy.argtypes = [ctypes.c_void_p]

    def decrypt(self, audio, ekey):
        kb = ekey.encode("ascii")
        ctx = self.Create(kb, len(kb))
        if not ctx:
            raise RuntimeError("CreateDecryption 返回 NULL（eKey 不是可用的 base64 原文？）")
        try:
            buf = ctypes.create_string_buffer(audio, len(audio))
            self.Decrypt(ctx, 0, buf, len(audio))
            return bytes(buf.raw[:len(audio)])
        finally:
            self.Destroy(ctx)


def parse_header(data):
    """解析 kgg 头部：返回 (audio_offset, audio_hash)，非 crypto_ver 5 返回 None。"""
    if data[:16] != KGM_MAGIC:
        return None
    audio_offset = int.from_bytes(data[0x10:0x14], "little")
    crypto_ver = int.from_bytes(data[0x14:0x18], "little")
    if crypto_ver != 5:
        return None
    pos = 0x3C + 8
    hash_len = int.from_bytes(data[pos:pos + 4], "little")
    audio_hash = data[pos + 4:pos + 4 + hash_len].decode("ascii", "replace")
    return audio_offset, audio_hash


def sniff_ext(data):
    if data.startswith(b"ID3"):
        return "mp3"
    if data.startswith((b"\xff\xfb", b"\xff\xf3", b"\xff\xfa")):
        return "mp3"
    if data.startswith(b"fLaC"):
        return "flac"
    if data.startswith(b"OggS"):
        return "ogg"
    return "bin"


def decrypt_one(fn, ekey_map, outdir, dll):
    with open(fn, "rb") as f:
        data = f.read()
    hdr = parse_header(data)
    if hdr is None:
        print(f"[跳过] {fn}: 不是 kgg (crypto_ver 5)")
        return False
    audio_offset, audio_hash = hdr
    ekey = ekey_map.get(audio_hash)
    if not ekey:
        print(f"[失败] {fn}: 数据库无 eKey (hash={audio_hash})")
        return False
    try:
        audio = dll.decrypt(data[audio_offset:], ekey)
    except Exception as exc:
        print(f"[失败] {fn}: {exc}")
        return False
    ext = sniff_ext(audio)
    if ext == "bin":
        print(f"[失败] {fn}: 无法识别音频格式")
        return False
    base = os.path.splitext(os.path.basename(fn))[0]
    out = os.path.join(outdir, base + "." + ext)
    with open(out, "wb") as f:
        f.write(audio)
    print(f"[成功] {os.path.basename(fn)} -> {base}.{ext}")
    return True


def main(argv=None):
    ap = argparse.ArgumentParser(description="酷狗 kgg 解密（QMDECRYPTION.dll，传 eKey 原文）")
    ap.add_argument("path", help="kgg 文件或目录")
    ap.add_argument("outdir", nargs="?", default="output", help="输出目录 (默认 output)")
    ap.add_argument("--db", help="指定 KGMusicV3.db 路径（也可用环境变量 KG_DB）")
    ap.add_argument("--dll", help="QMDECRYPTION.dll 路径（也可用环境变量 KG_DLL）")
    args = ap.parse_args(argv)

    dll_path = args.dll or find_dll()
    if not dll_path:
        sys.exit(f"未找到 {DLL_NAME}：用 --dll 指定，或设环境变量 KG_DLL（随酷狗安装）")
    print(f"DLL: {dll_path}")
    dll = Qmdll(dll_path)

    db = args.db or find_db()
    if not db:
        sys.exit("未找到 KGMusicV3.db：用 --db 或环境变量 KG_DB 指定")
    ekey_map = load_ekey_map(db)
    if ekey_map is None:
        sys.exit("数据库解密失败")
    print(f"数据库: {db} | eKey {len(ekey_map)} 个")

    os.makedirs(args.outdir, exist_ok=True)
    targets = iter_targets(args.path, recursive=True)
    if not targets:
        print("未找到 .kgg 文件")
        return
    ok = sum(1 for t in targets if decrypt_one(t, ekey_map, args.outdir, dll))
    print(f"\n完成: {ok}/{len(targets)} 成功")


if __name__ == "__main__":
    main()
