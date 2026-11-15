# 酷狗更新后如何应对（应对指南）

> 目标：酷狗版本更新/加密方案调整后，按本指南快速定位新方案。

## 快速定位流程

### 1. 确认是否只是版本变化（文件格式未变）

```bash
# 新版本安装目录里的 QMDECRYPTION.dll 是否还在、导出是否相同
python -c "
import struct
d = open(r'<新版>\QMDECRYPTION.dll','rb').read()
# 导出表解析... 检查 CreateDecryption/Decrypt/DestroyDecryption 是否仍在
"
```

如果导出不变 + KGM_MAGIC 不变（`7C D5 32 EB...`）→ **大概率算法没变**，
直接跑 `tools/kugou_dll.py`（DLL+eKey 原文，首选）或 `tools/kugou.py` 即可。

### 2. 若 KGM_MAGIC / crypto_ver 变了

- 看 `crypto_ver`（文件偏移 0x14）：
  - **5** = 新版 kgg（Map/RC4 + 数据库 eKey）
  - **3** = 旧版 kgma/kgm（**密钥内嵌 0x1C 16 字节** + table1/table2/MaskV2PreDef 流解密，用 `kgm_dec.c`）
  - 其他值 = 新的变体，需重新反汇编
- 换 ver 意味着新的算法分支，需重新反汇编 `QMDECRYPTION.dll` 的
  `Decrypt`(0x36D0)/`keystream`(0x3790)/RC4 批量(0x3350) 确认常数（如 71214、5120、128）

### 3. 若数据库结构变了（新字段/表名/加密方式）

- 重试 `kugou_dll.py`，若报"数据库解密失败"：
  - 检查 `KGMusicV3.db` 解密后是否仍是 `SQLite format 3\0`
  - 若否：master_key 或分页方案变了 → 重新在 `QMDECRYPTION.dll` / 主程序里找 AES key 常数
  - 表名/列名变了：`kugou_dll.py` 里 `ShareFileItems` / `EncryptionKeyId` / `EncryptionKey` 需调整

### 4. 若 eKey 派生变了（TEA key / 盐）

- 先确认是否仍能直接 `CreateDecryption(eKey原文)` 解（DLL 内部派生，省事）
- 若 DLL 不再接受 → 反查 `QMDECRYPTION.dll` 0x1C30 key 解析（base64/EncV2/普通分支）
- 若 EncV2 前缀多了（`QQMusic EncV2,Key:`）→ 走 v2 派生（kugou.py 已支持）
- 若 v1 的 `tan(106+i*0.1)` 盐值变 → 反汇编 `QMDECRYPTION.dll` 0x2020 处常量，或对照开源项目更新

## 关键指纹速查

| 指纹 | 位置 | 意义 |
|------|------|------|
| `7C D5 32 EB 86 02 7F 4B A8 AF A6 8E 0F FF 99 14` | KGG/kgma 头 0x00 | KGM Magic，变则格式换 |
| `0x400` | 头 0x10 | audio_offset / 头部大小 |
| `5` | 头 0x14 | crypto_ver 5 = 新版 kgg（数据库 eKey） |
| `3` | 头 0x14 | crypto_ver 3 = 旧版 kgma/kgm（**密钥内嵌 0x1C**） |
| 16 字节 key | kgma 头 0x1C | kgma 内嵌密钥（+补 0 共 17 字节） |
| audio_hash | kgg 头 0x48 | 数据库查询键 |
| `1D 61 31 45 B2 47 BF 7F ...` | 数据库 | AES master_key（24B） |
| 71214 / 5120 / 128 | 解密算法 | Map 常数 / RC4 段大小 |
| `tan(106 + i*0.1)` | eKey 派生 | v1 盐生成 |

## 开源参考

- `Aaron-gx/KGG-Decryptor`（GitHub，MIT）：Tauri/Rust 实现 kgg 算法，酷狗换版后常同步更新
- `AudioDecrypt`（GitHub）：`MusicDecryptor/Private/KGM.cpp` 提供 kgma/kgm 算法（table1/table2/MaskV2PreDef）
- 若仓库失效，可用本库 `02-algorithm.md` 的偏移表重新反汇编
