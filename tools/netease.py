#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
网易云音乐 NCM 音乐解密工具

原理 (ncmdump / 客户端逆向一致):
  1. 文件头: magic "CTENFDAM"(8) + 版本(2) + keydata_len(4) + keydata(128B)
  2. keydata 先 XOR 0x64, 再用固定 key sCoreKey 做 AES-128-ECB 解密
     得到 "neteasecloudmusic"+歌曲ID 明文, 取 [17:] 作为 RC4 密钥
  3. meta 段先 XOR 0x63, 去前缀 "163 key(Don't modify):", base64 解码,
     用固定 key sModifyKey 做 AES-128-ECB 解密, 去前缀 "music:" -> JSON
  4. 跳过 CRC32(4)+image_ver(1)+cover_frame_len(4)+img_len(4)+图片数据
  5. 剩余为加密音频: buildKeyBox(key) 生成 256 字节 S-box,
     逐字节 XOR 预计算的 T 表 (周期 256)
  6. 识别格式: 前 3 字节 ID3 -> mp3, 否则 fLaC -> flac
  7. 所有音质(高品质无损/无损/极高/标准)共用同一算法, 仅内部编码不同

依赖: pip install cryptography
用法:
  python tools/netease.py <ncm文件或目录> [输出目录] [-r]
"""
import sys, os, struct, base64, json, argparse

try:
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
except ImportError:
    sys.exit("缺少依赖 cryptography，请先执行: pip install cryptography")

NCM_MAGIC = b"CTENFDAM"
CORE_KEY = bytes([
    0x68, 0x7A, 0x48, 0x52, 0x41, 0x6D, 0x73, 0x6F,
    0x35, 0x6B, 0x49, 0x6E, 0x62, 0x61, 0x78, 0x57,
])  # hzHRAmsm5kInbaxW
MODIFY_KEY = bytes([
    0x23, 0x31, 0x34, 0x6C, 0x6A, 0x6B, 0x5F, 0x21,
    0x5C, 0x5D, 0x26, 0x30, 0x55, 0x3C, 0x27, 0x28,
])  # #14ljk_!\]&0U<'(
META_PREFIX = b"163 key(Don't modify):"
MUSIC_PREFIX = b"music:"
KEY_SKIP = 17
KEYBOX_SIZE = 256

def _aes_ecb_decrypt(key, data):
    dec = Cipher(algorithms.AES(key), modes.ECB()).decryptor().update(data)
    pad = dec[-1]
    if 0 < pad <= 16:
        dec = dec[:-pad]
    return dec

def _b64decode(data):
    return base64.b64decode(data + b"=" * ((4 - len(data) % 4) % 4))

def build_key_box(key):
    keybox = list(range(KEYBOX_SIZE))
    key_len = len(key)
    swap = c = last_byte = key_offset = 0
    for i in range(KEYBOX_SIZE):
        swap = keybox[i]
        c = (swap + last_byte + key[key_offset]) & 0xFF
        key_offset += 1
        if key_offset >= key_len:
            key_offset = 0
        keybox[i] = keybox[c]
        keybox[c] = swap
        last_byte = c
    return keybox

def build_xor_table(keybox):
    t = [0] * KEYBOX_SIZE
    for i in range(KEYBOX_SIZE):
        j = (i + 1) & 0xFF
        t[i] = keybox[(keybox[j] + keybox[(keybox[j] + j) & 0xFF]) & 0xFF]
    return t

def parse_meta(raw):
    """meta: XOR 0x63 -> 去前缀 -> base64 -> AES(MODIFY_KEY) -> 去 'music:' -> JSON"""
    data = bytes(b ^ 0x63 for b in raw)
    if not data.startswith(META_PREFIX):
        return None
    data = data[len(META_PREFIX):]
    dec = _aes_ecb_decrypt(MODIFY_KEY, _b64decode(data))
    if dec.startswith(MUSIC_PREFIX):
        dec = dec[len(MUSIC_PREFIX):]
    try:
        return json.loads(dec.decode('utf-8'))
    except Exception:
        return None

def decrypt_ncm(data):
    """返回 (音频明文bytes, meta dict 或 None, 封面bytes或None)"""
    if data[:8] != NCM_MAGIC:
        raise ValueError("不是 NCM 文件 (magic 不符)")
    pos = 8 + 2
    key_len = struct.unpack('<I', data[pos:pos+4])[0]
    pos += 4
    keydata = bytes(b ^ 0x64 for b in data[pos:pos+key_len])
    pos += key_len
    mkey = _aes_ecb_decrypt(CORE_KEY, keydata)
    rc4_key = mkey[KEY_SKIP:]

    meta_len = struct.unpack('<I', data[pos:pos+4])[0]
    pos += 4
    meta = parse_meta(data[pos:pos+meta_len]) if meta_len > 0 else None
    pos += meta_len

    pos += 5  # skip CRC32(4) + image version(1)
    cover_frame_len = struct.unpack('<I', data[pos:pos+4])[0]
    pos += 4
    img_len = struct.unpack('<I', data[pos:pos+4])[0]
    pos += 4
    cover = data[pos:pos+img_len] if img_len > 0 else None
    pos += img_len + max(0, cover_frame_len - img_len)

    audio = bytearray(data[pos:])
    t = build_xor_table(build_key_box(rc4_key))
    for i in range(len(audio)):
        audio[i] ^= t[i & 0xFF]
    return bytes(audio), meta, cover

def sniff_ext(data):
    if data.startswith(b"ID3"):
        return "mp3"
    if data.startswith(b"fLaC"):
        return "flac"
    if data.startswith(b"OggS"):
        return "ogg"
    return "bin"

def format_meta(meta):
    if not meta:
        return ""
    parts = []
    if meta.get("musicName"):
        parts.append(meta["musicName"])
    artist = meta.get("artist") or []
    names = []
    for a in artist:
        if a and a[0]:
            names.append(a[0])
    if names:
        parts.append(" / ".join(names))
    album = meta.get("album")
    if album:
        parts.append(album)
    bitrate = meta.get("bitrate")
    duration = meta.get("duration")
    if bitrate:
        parts.append(f"{bitrate // 1000}kbps")
    if duration:
        parts.append(f"{duration // 1000}s")
    return " | ".join(parts)

def decrypt_one(fn, outdir):
    with open(fn, "rb") as f:
        data = f.read()
    try:
        audio, meta, cover = decrypt_ncm(data)
    except ValueError as e:
        print(f"[跳过] {fn}: {e}")
        return False
    except Exception as e:
        print(f"[失败] {fn}: {e}")
        return False
    ext = sniff_ext(audio)
    if ext == "bin":
        print(f"[失败] {fn}: 无法识别音频格式")
        return False
    base = os.path.splitext(os.path.basename(fn))[0]
    out = os.path.join(outdir, base + "." + ext)
    with open(out, "wb") as f:
        f.write(bytes(audio))
    info = format_meta(meta)
    print(f"[成功] {fn} -> {out} ({ext.upper()}){ '  ' + info if info else ''}")
    return True


def iter_targets(path, recursive=True):
    """展开待处理文件：目录按 .ncm 筛选（可选递归），文件原样返回。"""
    if os.path.isdir(path):
        if recursive:
            return [os.path.join(dp, fn) for dp, _dn, fns in os.walk(path)
                    for fn in fns if fn.lower().endswith(".ncm")]
        return [os.path.join(path, fn) for fn in os.listdir(path) if fn.lower().endswith(".ncm")]
    return [path]


def main(argv=None):
    ap = argparse.ArgumentParser(description="网易云音乐 NCM 音乐解密工具")
    ap.add_argument("path", help="NCM 文件或目录")
    ap.add_argument("outdir", nargs="?", default="output", help="输出目录 (默认 output)")
    ap.add_argument("-r", "--recursive", action="store_true", help="目录输入时递归子目录")
    args = ap.parse_args(argv)

    os.makedirs(args.outdir, exist_ok=True)
    targets = iter_targets(args.path, args.recursive)
    if not targets:
        print("未找到 .ncm 文件")
        return
    ok = sum(1 for t in targets if decrypt_one(t, args.outdir))
    print(f"\n完成: {ok}/{len(targets)} 成功")

if __name__ == "__main__":
    main()
