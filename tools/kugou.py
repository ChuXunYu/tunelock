#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KuGou KGG 音乐解密工具
基于 KGMusicV3.db 中的 eKey 解密 .kgg 文件 (crypto version 5)

原理：
  1. KGG 文件头(0x400字节) 含 audio_hash (偏移 0x48)
  2. 酷狗本地数据库 KGMusicV3.db (AES-128-CBC 分页加密) 的 ShareFileItems 表
     以 EncryptionKeyId=audio_hash 存放 eKey
  3. eKey 经 TEA(Base64多层) 派生得到 512 字节原始密钥
  4. 密钥长度 > 300 -> RC4Cipher, 否则 MapCipher
  5. 对文件[0x400:] 从偏移 0 解密, 自动识别输出格式 (FLAC/OGG/MP3)

依赖: pip install cryptography
用法:
  python tools/kugou.py <kgg文件或目录> [输出目录] [--db DB] [-r]

说明: 需要本机酷狗数据库里有该歌的 eKey（酷狗能播的歌即可解密），
      纯 Python 实现，不依赖任何腾讯 DLL——与 kugou_dll.py 互为独立校验路径。
"""
import sys, os, struct, base64, math, sqlite3, tempfile
import argparse

try:
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.primitives import hashes
except ImportError:
    sys.exit("缺少依赖 cryptography，请先执行: pip install cryptography")

# ---------- 常量 ----------
PAGE_SIZE = 0x400
SQLITE_HEADER = b"SQLite format 3\x00"
TEA_DELTA = 0x9E3779B9
KGM_MAGIC = bytes([0x7C,0xD5,0x32,0xEB,0x86,0x02,0x7F,0x4B,
                   0xA8,0xAF,0xA6,0x8E,0x0F,0xFF,0x99,0x14])
DEFAULT_MASTER_KEY = bytes([
    0x1D,0x61,0x31,0x45,0xB2,0x47,0xBF,0x7F,
    0x3D,0x18,0x96,0x72,0x14,0x4F,0xE4,0xBF,
    0x00,0x00,0x00,0x00,0x73,0x41,0x6C,0x54,
])
M32 = 0xFFFFFFFF

# ---------- 数据库解密 (AES-128-CBC 分页) ----------
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

# ---------- key 派生 (TEA) ----------
def _tea_decrypt_block(block, key):
    v0 = struct.unpack('>I', block[0:4])[0]
    v1 = struct.unpack('>I', block[4:8])[0]
    k = [struct.unpack('>I', key[i:i+4])[0] for i in (0, 4, 8, 12)]
    s = (TEA_DELTA * 16) & M32
    for _ in range(16):
        t = ((((v0 << 4) + k[2]) & M32) ^ ((v0 + s) & M32) ^ (((v0 >> 5) + k[3]) & M32)) & M32
        v1 = (v1 - t) & M32
        t = ((((v1 << 4) + k[0]) & M32) ^ ((v1 + s) & M32) ^ (((v1 >> 5) + k[1]) & M32)) & M32
        v0 = (v0 - t) & M32
        s = (s - TEA_DELTA) & M32
    return struct.pack('>II', v0, v1)

def _decrypt_tencent_tea(inp, key):
    SALT_LEN, ZERO_LEN = 2, 7
    if len(inp) % 8 != 0 or len(inp) < 16:
        return None
    dest = bytearray(_tea_decrypt_block(inp[:8], key))
    pad_len = dest[0] & 0x7
    out_len = len(inp) - 1 - pad_len - SALT_LEN - ZERO_LEN
    if out_len < 0:
        return None
    out = bytearray(out_len)
    iv_prev = bytearray(8)
    iv_cur = bytearray(inp[:8])
    in_pos, dest_idx = 8, 1 + pad_len

    def crypt_block():
        nonlocal in_pos, dest_idx, iv_prev, iv_cur, dest
        iv_prev, iv_cur = iv_cur, bytearray(inp[in_pos:in_pos+8])
        for i in range(8):
            dest[i] ^= iv_cur[i]
        dest = bytearray(_tea_decrypt_block(bytes(dest), key))
        in_pos += 8
        dest_idx = 0

    i = 1
    while i <= SALT_LEN:
        if dest_idx < 8:
            dest_idx += 1; i += 1
        else:
            crypt_block()
    out_pos = 0
    while out_pos < out_len:
        if dest_idx < 8:
            out[out_pos] = dest[dest_idx] ^ iv_prev[dest_idx]
            dest_idx += 1; out_pos += 1
        else:
            crypt_block()
    return bytes(out)

def _simple_make_key(salt, length):
    return [int(abs(math.tan(salt + i * 0.1)) * 100.0) & 0xFF for i in range(length)]

def derive_key_v1(raw):
    sk = _simple_make_key(106, 8)
    tea_key = bytearray(16)
    for i in range(8):
        tea_key[i*2], tea_key[i*2+1] = sk[i], raw[i]
    dec = _decrypt_tencent_tea(raw[8:], bytes(tea_key))
    if dec is None:
        return None
    return raw[:8] + dec

def derive_key_v2(raw):
    k1 = bytes([0x33,0x38,0x36,0x5A,0x4A,0x59,0x21,0x40,0x23,0x2A,0x24,0x25,0x5E,0x26,0x29,0x28])
    k2 = bytes([0x2A,0x2A,0x23,0x21,0x28,0x23,0x24,0x25,0x26,0x5E,0x61,0x31,0x63,0x5A,0x2C,0x54])
    buf = _decrypt_tencent_tea(raw, k1)
    if buf is None: return None
    buf = _decrypt_tencent_tea(buf, k2)
    if buf is None: return None
    try:
        return base64.b64decode(buf)
    except Exception:
        return None

def derive_key(ekey):
    raw = base64.b64decode(ekey)
    v2 = b"QQMusic EncV2,Key:"
    if raw.startswith(v2):
        raw = derive_key_v2(raw[len(v2):])
        if raw is None: return None
    return derive_key_v1(raw)

# ---------- 解密器 ----------
def _ror8(v, r):
    r %= 8
    return ((v >> r) | ((v << (8 - r)) & 0xFF)) & 0xFF

class MapCipher:
    def __init__(self, key):
        self.key, self.size = key, len(key)
    def mask(self, offset):
        if offset > 0x7FFF:
            offset %= 0x7FFF
        idx = (offset * offset + 71214) % self.size
        return _ror8(self.key[idx], ((idx & 0x7) + 4) % 8)
    def decrypt(self, buf, offset):
        for i in range(len(buf)):
            buf[i] ^= self.mask(offset + i)

class Rc4Cipher:
    SEG, FIRST = 5120, 128
    def __init__(self, key):
        self.key, self.n = key, len(key)
        bx = [(i & 0xFF) for i in range(self.n)]
        j = 0
        for i in range(self.n):
            j = (j + bx[i] + key[i % self.n]) % self.n
            bx[i], bx[j] = bx[j], bx[i]
        self.bx = bx
        h = 1
        for i in range(self.n):
            v = key[i]
            if v == 0: continue
            nxt = (h * v) & M32
            if nxt == 0 or nxt <= h: break
            h = nxt
        self.hash = h
    def seg_skip(self, sid):
        denom = (sid + 1) * self.key[sid % self.n]
        if denom == 0: return 0
        v = self.hash / denom * 100.0
        if math.isnan(v) or math.isinf(v): return 0
        return int(v) % self.n
    def decrypt(self, buf, offset):
        off, done, togo = offset, 0, len(buf)
        if off < self.FIRST:
            sz = min(togo, self.FIRST - off)
            self.enc_first(buf, done, sz, off)
            off += sz; togo -= sz; done += sz
        if togo > 0 and off % self.SEG != 0:
            sz = min(togo, self.SEG - off % self.SEG)
            self.enc_seg(buf, done, sz, off)
            off += sz; togo -= sz; done += sz
        while togo > self.SEG:
            self.enc_seg(buf, done, self.SEG, off)
            off += self.SEG; togo -= self.SEG; done += self.SEG
        if togo > 0:
            self.enc_seg(buf, done, togo, off)
    def enc_first(self, buf, start, size, offset):
        for i in range(size):
            buf[start+i] ^= self.key[self.seg_skip(offset + i)]
    def enc_seg(self, buf, start, size, offset):
        bx = self.bx[:]
        j = k = 0
        skip = (offset % self.SEG) + self.seg_skip(offset // self.SEG)
        n = self.n
        for i in range(-skip, size):
            j = (j + 1) % n
            k = (bx[j] + k) % n
            bx[j], bx[k] = bx[k], bx[j]
            if i >= 0:
                buf[start+i] ^= bx[(bx[j] + bx[k]) % n]

# ---------- 主流程 ----------
def find_db():
    """定位酷狗 eKey 数据库。

    查找顺序：环境变量 ``KG_DB`` → ``%APPDATA%\\KuGou8`` → ``%LOCALAPPDATA%\\KuGou8`` → 当前目录。
    想固定路径就设 ``KG_DB=D:\\path\\KGMusicV3.db``，不必每次传 ``--db``。
    """
    env = os.environ.get("KG_DB")
    if env and os.path.isfile(env):
        return env
    cands = []
    for var, sub in (("APPDATA", "KuGou8"), ("LOCALAPPDATA", "KuGou8")):
        base = os.environ.get(var, "")
        if base:
            cands.append(os.path.join(base, sub))
    cands.append(".")
    for d in cands:
        if not os.path.isdir(d):
            continue
        for fn in os.listdir(d):
            if "KGMusicV3" in fn and fn.lower().endswith(".db"):
                return os.path.join(d, fn)
    return None

def load_ekey_map(db_path):
    """把加密的 KGMusicV3.db 解成明文 SQLite，读出 audio_hash -> eKey 映射。

    临时明文库用完即删（里面是整库 eKey，不该留在 %TEMP% 里）。
    """
    with open(db_path, "rb") as f:
        raw = f.read()
    plain = decrypt_database(raw)
    if not plain.startswith(SQLITE_HEADER):
        return None
    fd, tmp = tempfile.mkstemp(prefix="kg_plain_", suffix=".db")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(plain)
        conn = sqlite3.connect(tmp)
        try:
            rows = conn.execute(
                "SELECT EncryptionKeyId, EncryptionKey FROM ShareFileItems "
                "WHERE EncryptionKey IS NOT NULL AND EncryptionKey != ''").fetchall()
        except sqlite3.Error:
            return {}
        finally:
            conn.close()
        return {k: v for k, v in rows}
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass

def iter_targets(path, recursive=True):
    """展开待处理文件：目录则按扩展名筛选，文件则原样返回。"""
    if os.path.isdir(path):
        if recursive:
            return [os.path.join(dp, fn) for dp, _dn, fns in os.walk(path)
                    for fn in fns if fn.lower().endswith(".kgg")]
        return [os.path.join(path, fn) for fn in os.listdir(path) if fn.lower().endswith(".kgg")]
    return [path]

def parse_header(data):
    if data[:16] != KGM_MAGIC:
        return None
    audio_offset = struct.unpack('<I', data[0x10:0x14])[0]
    crypto_ver = struct.unpack('<I', data[0x14:0x18])[0]
    if crypto_ver != 5:
        return None, crypto_ver
    pos = 0x3C + 8
    hash_len = struct.unpack('<I', data[pos:pos+4])[0]
    audio_hash = data[pos+4:pos+4+hash_len].decode('ascii', 'replace')
    return (audio_offset, audio_hash), crypto_ver

def sniff_ext(data):
    if data.startswith(b"ID3"): return "mp3"
    if data.startswith((b"\xff\xfb", b"\xff\xf3", b"\xff\xfa")): return "mp3"
    if data.startswith(b"fLaC"): return "flac"
    if data.startswith(b"OggS"): return "ogg"
    return "bin"

def decrypt_one(fn, ekey_map, outdir):
    with open(fn, "rb") as f:
        data = f.read()
    hdr = parse_header(data)
    if hdr is None:
        print(f"[跳过] {fn}: 不是 KGG 文件")
        return False
    (audio_offset, audio_hash), crypto_ver = hdr
    if crypto_ver != 5:
        print(f"[失败] {fn}: 不支持的 crypto version {crypto_ver}")
        return False
    ekey = ekey_map.get(audio_hash)
    if not ekey:
        print(f"[失败] {fn}: 数据库无 eKey (hash={audio_hash})")
        return False
    raw_key = derive_key(ekey)
    if raw_key is None:
        print(f"[失败] {fn}: key 派生失败")
        return False
    cipher = Rc4Cipher(raw_key) if len(raw_key) > 300 else MapCipher(raw_key)
    audio = bytearray(data[audio_offset:])
    cipher.decrypt(audio, 0)
    ext = sniff_ext(bytes(audio))
    if ext == "bin":
        print(f"[失败] {fn}: 无法识别音频格式")
        return False
    base = os.path.splitext(os.path.basename(fn))[0]
    out = os.path.join(outdir, base + "." + ext)
    with open(out, "wb") as f:
        f.write(bytes(audio))
    print(f"[成功] {fn} -> {out} ({ext.upper()})")
    return True

def main(argv=None):
    ap = argparse.ArgumentParser(description="KuGou KGG 音乐解密工具")
    ap.add_argument("path", help="KGG 文件或目录")
    ap.add_argument("outdir", nargs="?", default="output", help="输出目录 (默认 output)")
    ap.add_argument("--db", help="指定 KGMusicV3.db 路径（也可用环境变量 KG_DB）")
    ap.add_argument("-r", "--recursive", action="store_true", help="目录输入时递归子目录")
    args = ap.parse_args(argv)

    db = args.db or find_db()
    if not db:
        sys.exit("未找到 KGMusicV3.db (位于 %APPDATA%\\KuGou8)；用 --db 或环境变量 KG_DB 指定")
    print(f"数据库: {db}")
    ekey_map = load_ekey_map(db)
    if ekey_map is None:
        sys.exit("数据库解密失败")
    print(f"已加载 {len(ekey_map)} 个 eKey")

    os.makedirs(args.outdir, exist_ok=True)
    targets = iter_targets(args.path, args.recursive)
    if not targets:
        print("未找到 .kgg 文件")
        return
    ok = sum(1 for t in targets if decrypt_one(t, ekey_map, args.outdir))
    print(f"\n完成: {ok}/{len(targets)} 成功")

if __name__ == "__main__":
    main()
