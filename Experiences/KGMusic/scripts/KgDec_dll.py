#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
酷狗 kgg 解密工具 (推荐路径: QMDECRYPTION.dll)

关键修正 (2026-08-10):
  CreateDecryption 应传入数据库 eKey 的 **base64 原文**(字符串),
  DLL 内部自行 base64 解码 + TEA 派生 + 构建解密器。
  不要传派生的二进制 key (会乱码)。

用法:
  python KgDec_dll.py <kgg文件或目录> [输出目录]

依赖:
  - cryptography (解密 KGMusicV3.db 查 eKey)
  - QMDECRYPTION.dll (E:\\KGMusic\\...\\QMDECRYPTION.dll, x64, 随酷狗安装)
"""
import sys, os, struct, glob, ctypes, tempfile
import argparse

try:
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.primitives import hashes
except ImportError:
    sys.exit("缺少依赖 cryptography，请先执行: pip install cryptography")

DEFAULT_DLL = r"E:\KGMusic\20.1.41.27870\QMDECRYPTION.dll"
PAGE_SIZE = 0x400
SQLITE_HEADER = b"SQLite format 3\x00"
DEFAULT_MASTER_KEY = bytes([
    0x1D,0x61,0x31,0x45,0xB2,0x47,0xBF,0x7F,
    0x3D,0x18,0x96,0x72,0x14,0x4F,0xE4,0xBF,
    0x00,0x00,0x00,0x00,0x73,0x41,0x6C,0x54,
])
M32 = 0xFFFFFFFF

# ---------- 数据库解密 (同 KgDec.py) ----------
def _md5(data):
    h = hashes.Hash(hashes.MD5()); h.update(data); return h.finalize()

def _derive_iv_seed(seed):
    left = (seed * 0x9EF4) & M32
    right = ((seed // 0xCE26) * 0x7FFFFF07) & M32
    value = (left - right) & M32
    return value if value & 0x80000000 == 0 else (value + 0x7FFFFF07) & M32

def _derive_page_iv(page):
    iv = bytearray(16); p = page + 1
    for i in range(0, 16, 4):
        p = _derive_iv_seed(p)
        iv[i:i+4] = struct.pack('<I', p)
    return _md5(bytes(iv))

def _derive_page_key(page):
    mk = bytearray(DEFAULT_MASTER_KEY)
    mk[0x10:0x14] = struct.pack('<I', page)
    return _md5(bytes(mk))

def _aes_cbc_dec(data, key, iv):
    d = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
    return d.update(data) + d.finalize()

def _decrypt_page1(buf):
    o10 = struct.unpack('<I', buf[0x10:0x14])[0]
    o14 = struct.unpack('<I', buf[0x14:0x18])[0]
    v6 = (((o10 & 0xFF) << 8) | ((o10 & 0xFF00) << 16)) & M32
    if not (o14 == 0x20204000 and ((v6 - 0x200) & M32) <= 0xFE00 and ((v6 - 1) & v6) == 0):
        return
    buf[0x10:0x18] = buf[0x08:0x10]
    key, iv = _derive_page_key(1), _derive_page_iv(1)
    dec = _aes_cbc_dec(bytes(buf[0x10:PAGE_SIZE]), key, iv)
    buf[0x10:PAGE_SIZE] = dec
    buf[0:16] = SQLITE_HEADER

def decrypt_database(data):
    if data.startswith(SQLITE_HEADER):
        return data
    buf = bytearray(data)
    _decrypt_page1(buf)
    n = len(buf) // PAGE_SIZE
    for pg in range(2, n + 1):
        off = (pg - 1) * PAGE_SIZE
        key, iv = _derive_page_key(pg), _derive_page_iv(pg)
        buf[off:off+PAGE_SIZE] = _aes_cbc_dec(bytes(buf[off:off+PAGE_SIZE]), key, iv)
    return bytes(buf)

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
        kb = ekey.encode('ascii')
        ctx = self.Create(kb, len(kb))
        try:
            buf = ctypes.create_string_buffer(audio, len(audio))
            self.Decrypt(ctx, 0, buf, len(audio))
            return bytes(buf.raw[:len(audio)])
        finally:
            self.Destroy(ctx)

def load_ekey_map(db_path):
    plain = decrypt_database(open(db_path, "rb").read())
    if not plain.startswith(SQLITE_HEADER):
        return None
    tmp = os.path.join(tempfile.gettempdir(), "kg_dll_plain.db")
    open(tmp, "wb").write(plain)
    import sqlite3
    conn = sqlite3.connect(tmp)
    try:
        rows = conn.execute(
            "SELECT EncryptionKeyId, EncryptionKey FROM ShareFileItems "
            "WHERE EncryptionKey IS NOT NULL AND EncryptionKey != ''").fetchall()
    except sqlite3.Error:
        rows = []
    conn.close()
    return {k: v for k, v in rows}

def parse_header(data):
    KGM_MAGIC = bytes([0x7C,0xD5,0x32,0xEB,0x86,0x02,0x7F,0x4B,
                       0xA8,0xAF,0xA6,0x8E,0x0F,0xFF,0x99,0x14])
    if data[:16] != KGM_MAGIC:
        return None
    audio_offset = struct.unpack('<I', data[0x10:0x14])[0]
    crypto_ver = struct.unpack('<I', data[0x14:0x18])[0]
    if crypto_ver != 5:
        return None
    pos = 0x3C + 8
    hash_len = struct.unpack('<I', data[pos:pos+4])[0]
    audio_hash = data[pos+4:pos+4+hash_len].decode('ascii', 'replace')
    return (audio_offset, audio_hash)

def sniff_ext(data):
    if data.startswith(b"ID3"): return "mp3"
    if data.startswith((b"\xff\xfb", b"\xff\xf3", b"\xff\xfa")): return "mp3"
    if data.startswith(b"fLaC"): return "flac"
    if data.startswith(b"OggS"): return "ogg"
    return "bin"

def decrypt_one(fn, ekey_map, outdir, dll):
    data = open(fn, "rb").read()
    hdr = parse_header(data)
    if hdr is None:
        print(f"[跳过] {fn}: 不是 kgg (crypto_ver 5)")
        return False
    audio_offset, audio_hash = hdr
    ekey = ekey_map.get(audio_hash)
    if not ekey:
        print(f"[失败] {fn}: 数据库无 eKey (hash={audio_hash})")
        return False
    audio = dll.decrypt(data[audio_offset:], ekey)
    ext = sniff_ext(audio)
    if ext == "bin":
        print(f"[失败] {fn}: 无法识别音频格式")
        return False
    base = os.path.splitext(os.path.basename(fn))[0]
    out = os.path.join(outdir, base + "." + ext)
    open(out, "wb").write(audio)
    print(f"[成功] {os.path.basename(fn)} -> {base}.{ext}")
    return True

def main():
    ap = argparse.ArgumentParser(description="酷狗 kgg 解密 (QMDECRYPTION.dll, eKey 原文)")
    ap.add_argument("path", help="kgg 文件或目录")
    ap.add_argument("outdir", nargs="?", default="output", help="输出目录 (默认 output)")
    ap.add_argument("--db", help="指定 KGMusicV3.db 路径")
    ap.add_argument("--dll", default=DEFAULT_DLL, help="QMDECRYPTION.dll 路径")
    args = ap.parse_args()

    if not os.path.exists(args.dll):
        sys.exit(f"未找到 QMDECRYPTION.dll: {args.dll} (请在 --dll 指定)")
    dll = Qmdll(args.dll)

    db = args.db
    if not db:
        ad = os.environ.get("APPDATA", "")
        for cand in (os.path.join(ad, "KuGou8"), "."):
            if os.path.isdir(cand):
                for fn in os.listdir(cand):
                    if "KGMusicV3" in fn and fn.lower().endswith(".db"):
                        db = os.path.join(cand, fn); break
            if db: break
    if not db:
        sys.exit("未找到 KGMusicV3.db")
    ekey_map = load_ekey_map(db)
    if ekey_map is None:
        sys.exit("数据库解密失败")
    print(f"数据库: {db} | eKey {len(ekey_map)} 个")

    os.makedirs(args.outdir, exist_ok=True)
    targets = []
    if os.path.isdir(args.path):
        for dp, dn, fn in os.walk(args.path):
            for f in fn:
                if f.lower().endswith(".kgg"):
                    targets.append(os.path.join(dp, f))
    else:
        targets = [args.path]
    ok = sum(1 for t in targets if decrypt_one(t, ekey_map, args.outdir, dll))
    print(f"\n完成: {ok}/{len(targets)} 成功")

if __name__ == "__main__":
    main()
