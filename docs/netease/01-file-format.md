# 01 - NCM 文件格式分析

版本基线：网易云 3.1.37.205354，样本 4 个（四种音质各一）。

## 1. 总体布局

```
偏移      长度   内容
0x00      8      magic "CTENFDAM"
0x08      2      版本号 (样本为 01 70)
0x0A      4      keydata_len (样本恒为 0x80=128)
0x0E      keydata_len  keydata（加密的 RC4 密钥，128 字节）
0x0E+len  4      meta_len（样本 622~726 不等）
          4      meta_len  加密 meta（"163 key(Don't modify):" 体系）
          5      CRC32(4) + image version(1)
          4      cover_frame_len（封面帧总长）
          4      img_len（封面图数据长度，通常 = cover_frame_len）
          img_len  封面图数据（PNG `89 50 4E` 或 JPEG `FF D8 FF`）
          剩余    加密音频流
```

## 2. 关键字段

### 2.1 keydata（偏移 0x0E，长 0x80）

4 个样本 keydata 前 16 字节**完全相同**：`2C CE D5 EB 69 EA FB 14 55 0D 45 BF 61 DD 17 1D`。
原因：keydata 是 AES-ECB 加密的，明文字节 `neteasecloudmusi`（16 字节固定前缀）加密后相同。

解密后明文形态（见 02 文档）：
```
neteasecloudmusic <歌曲ID数字串> <填充>
```
前 17 字节跳过，`[17:]` 作为 RC4 密钥（每个文件不同 → 音频密钥流不同）。

### 2.2 meta（明文 protobuf 假象）

meta 区直接看是 `52 55 50 43 08 06 1A 4B ...`（"RUPC" + 类 protobuf 头）。
逐字节 XOR 0x63 后变为 `31 36 33 20 ...` = `"163 key(Don't modify):"`。

meta 解密链（见 02 文档 §2）：
```
XOR 0x63 → 去前缀(22B) → base64 → AES-ECB(sModifyKey) → 去前缀 "music:" → JSON
```

### 2.3 封面

meta 之后：`CRC32(4) + image_ver(1) + cover_frame_len(4) + img_len(4) + 图片数据`。
样本中 cover_frame_len 与 img_len 相等（无额外对齐字节）。
- 林俊杰样本封面为 PNG，其余为 JPEG。

## 3. 四种音质样本

| 音质 | 文件大小 | meta_len | meta bitrate | 输出 |
|------|---------|----------|--------------|------|
| 高品质无损 (林俊杰) | 31,540,456 | 0x2D6 | 999000 | FLAC 16-bit |
| 无损 (Charlie Puth) | 41,014,907 | 0x2AE | 999000 | FLAC 24-bit |
| 极高 (Muyoi) | 10,085,829 | 0x282 | 320000 | MP3 320k |
| 标准 (YOASOBI) | 6,895,516 | 0x26E | 128000 | MP3 128k |

> meta JSON 的 `bitrate` 是音质档位的最可靠来源（999000=无损系，320000=极高，128000=标准）。

## 4. 定位脚本要点

- magic 用 `"CTENFDAM"`（客户端 isNcmFile 按两个 4 字节比较 0x4E455443 / 0x4D414446）
- 4 字节长度字段一律小端
- 音频数据起始 = 封面数据结束后（`img_len` 之后，若 cover_frame_len>img_len 再跳过差值）
