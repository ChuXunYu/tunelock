# 02 - 算法逆向记录

## 1. 常量定位（cloudmusic.dll，x64）

安装目录全盘扫描字符串，`cloudmusic.dll`（34208768 B，image_base 0x180000000）命中：

| 字符串/常量 | 文件偏移 | 含义 |
|------------|---------|------|
| `hzHRAmsm5kInbaxW` (0x68 0x7A ... 0x57) | 0x18D9AA0 | **sCoreKey**：解密 keydata 的 AES-128 key |
| `#14ljk_!\]&0U<'(` (0x23 0x31 ... 0x28) | 0x173E940 | **sModifyKey**：解密 meta 的 AES-128 key |
| `neteasecloudmusic` | 0x173F8A8 | keydata 解密后的明文前缀 |
| `163 key(Don't modify):` | 0x173E928 | meta XOR 0x63 后的明文前缀 |
| AES S-box (0x63 0x7C 0x77 0x7B...) | 0x18DC5A0 | 内置 AES 实现佐证 |

> `CTENFDAM` / `RUPC` 均不在任何二进制中：magic 在客户端按 4 字节常数比较，
> `RUPC` 只是 `"163 "` XOR 0x63 的密文形态，均为运行时构造。

## 2. 解密链

### 2.1 keydata → RC4 key

```
keydata[128] 逐字节 XOR 0x64
AES-128-ECB(sCoreKey) 解密 (含 PKCS7 unpad)
  → "neteasecloudmusic" + 歌曲ID数字串 + 填充
rc4_key = 解密结果[17:]      # 跳过 17 字节 (16 字节前缀 + 1)
```

实测 4 样本解密结果前缀：
```
neteasecloudmusic170302...  (Charlie Puth)
neteasecloudmusic118027...  (Muyoi)
neteasecloudmusic188916...  (YOASOBI)
neteasecloudmusic690916...  (林俊杰)
```

### 2.2 meta → JSON

```
meta 逐字节 XOR 0x63
去前缀 "163 key(Don't modify):" (22B)
base64 解码
AES-128-ECB(sModifyKey) 解密 (含 unpad)
去前缀 "music:" (6B)
→ JSON { musicName, album, artist[][], bitrate, duration, format }
```

### 2.3 音频流解密（buildKeyBox + XOR 表）

`buildKeyBox(key, keyLen)`（类 RC4 KSA 变体）：

```
S[i] = i  (i=0..255)
swap=0; c=0; last_byte=0; key_offset=0
for i in 0..255:
    swap = S[i]
    c = (swap + last_byte + key[key_offset++]) & 0xFF; key_offset %= keyLen
    S[i] = S[c]; S[c] = swap; last_byte = c
```

逐字节解密（音频偏移从 0 开始）：

```
for i in 0..len-1:
    j = (i + 1) & 0xFF
    buf[i] ^= S[(S[j] + S[(S[j] + j) & 0xFF]) & 0xFF]
```

由于索引只依赖 `i & 0xFF`，可预计算 256 字节 XOR 表 T：

```
T[i] = S[(S[(i+1)&0xFF] + S[(S[(i+1)&0xFF] + (i+1)&0xFF) & 0xFF]) & 0xFF]
buf[i] ^= T[i & 0xFF]
```

> ncmdump 按 0x8000 字节分块处理，块内 i 从 0 重计；因 T 周期为 256，与全程连续等价。

## 3. 音质与算法关系

- **四档音质共用完全相同的加密算法**，差异仅在加密前的音频规格（FLAC 位深/MP3 码率）。
- 解密产物识别：前 3 字节 `ID3` → mp3；`fLaC` → flac；`OggS` → ogg。
- meta JSON `bitrate`：999000=无损系(FLAC)、320000=极高、128000=标准。

## 4. 交叉验证

| 手段 | 结果 |
|------|------|
| 开源工具 `taurusxin/ncmdump` v1.5.1 | 4/4 文件解密成功 |
| FLAC 对比 | 我的输出与 ncmdump 的 STREAMINFO(前 42B) 逐字节一致 |
| MP3 对比 | 各自跳过 ID3v2 后音频帧前 1KB 与尾部 256B 完全一致 |
| DLL 常量 | sCoreKey/sModifyKey/neteasecloudmusic 全部以明文存在于 cloudmusic.dll .rdata |
