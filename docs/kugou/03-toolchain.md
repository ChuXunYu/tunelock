# 酷狗 KGG / kgma 解密工具构建

## 工具一览

| 工具 | 格式 | 方式 | 说明 |
|------|------|------|------|
| `tools/kugou_dll.py` | kgg | **推荐** | ctypes 调 `QMDECRYPTION.dll`，`CreateDecryption(eKey原文)`，256/512 key 通吃、快 |
| `tools/kugou.py` | kgg | 纯 Python | 自实现 RC4/Map（无 DLL 依赖），可作为 DLL 不可用时的备选 |
| `tools/native/kugou/kgm_dec.c`（+ `bin/kgm_dec.exe`） | kgma/kgm | C | 密钥内嵌文件头，三张 272 字节表流解密，递归目录批量 |

## kgg 解密：两种路径

### 路径 A（推荐）：`QMDECRYPTION.dll`（kugou_dll.py）

**关键**：`CreateDecryption` 传入**数据库 eKey 的 base64 原文**（字符串），DLL 内部解码+TEA 派生。

```python
dll = ctypes.CDLL(r"E:\KGMusic\20.1.41.27870\QMDECRYPTION.dll")
ctx = dll.CreateDecryption(ekey_bytes, len(ekey_bytes))   # ekey = 数据库 EncryptionKey
buf = ctypes.create_string_buffer(audio, len(audio))       # audio = 文件[audio_offset:]
dll.Decrypt(ctx, 0, buf, len(audio))
# buf.raw[:len] 即解密结果
```

```bash
python tools/kugou_dll.py "path\song.kgg" "outdir" [--db 数据库] [--dll DLL路径]
```

> 不要传派生的二进制 key（乱码）。`DestroyDecryption` 需声明 `argtypes=[c_void_p]`。
> 实测 142/142 kgg 全解出 FLAC，256 与 512 key 均可。

### 路径 B：纯 Python（kugou.py）

自实现：数据库 AES 分页解密 → 查 eKey → TEA 派生 → RC4/Map 解密。

```bash
python tools/kugou.py "path\song.kgg" "outdir" [--db 数据库]
```

## kgma / kgm 解密（kgm_dec.c）

密钥内嵌文件头（0x1C 处 16 字节 + 补 0 共 17 字节），无需数据库。

```bash
pwsh -File build\build.ps1 -Target kgm    # 或 bash build/build.sh kgm
kgm_dec.exe <输入目录> <输出目录>      # 递归处理 *.kgma / *.kgm
```

算法要点（见 02 文档）：
```
med8 = key[pos%17] ^ b;  med8 ^= (med8&15)<<4
msk8 = 0; off = pos>>4
while off >= 0x11: msk8 ^= table1[off%272]; off>>=4; msk8 ^= table2[off%272]; off>>=4
msk8 = MaskV2PreDef[pos%272] ^ msk8;  msk8 ^= (msk8&15)<<4
buf[pos] = med8 ^ msk8
```

## 依赖

```bash
pip install cryptography        # 数据库解密（kugou 系列）
# kgm_dec.c 用任意 mingw64 gcc 就能编（bin/ 里已带一个编译好的）
```

## 历史决策记录（已修正）

> 早期结论"QMDECRYPTION.dll 不能直接调"是错误的（当时传了派生的二进制 key）。
> 修正为传 eKey base64 原文后，DLL 路径成为首选（快且通吃所有 key 长度）。

## 已验证输出

| 输入 | 输出 | 采样 |
|------|------|------|
| Free Loop.kgg (40MB) | FLAC | 44100Hz / 2ch |
| 142 个 kgg（256/512 key） | 全 FLAC | 44100~48000Hz / 2ch |
| 167 个 kgma | 全 FLAC | 44100Hz / 2ch |
