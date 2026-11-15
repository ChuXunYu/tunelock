# 逆向笔记索引

> 腾讯系 / 酷狗系 / 网易系音乐客户端「加密封装音频」的逆向方法、算法结论与离线解密路径。
> 目标：平台更新、加密方案调整后，能基于这里快速定位变更点并更新工具，而不是从头再来一遍。

## 目录结构

```
docs/
├── README.md              ← 本索引（平台对比 + 通用方法论）
├── gui.md                 GUI 与命令行用法
├── qqmusic/               腾讯 QQ 音乐 mflac / mgg
│   ├── README.md          核心结论、版本基线、踩坑
│   ├── 01-file-format.md  文件结构、尾部元数据块
│   ├── 02-algorithm.md    EncAndDesMediaFile / CommonFunction.dll 算法
│   ├── 03-toolchain.md    C 原生方案、msys2 工具链、Unicode、性能
│   ├── 04-version-update.md 版本更新后的指纹速查
│   └── tool-native.md     QqmDec.exe 的编译、用法与验证数据
├── kugou/                 酷狗 KGG / kgma / kgm
│   ├── README.md
│   ├── 01-file-format.md  KGM 头部、audio_hash
│   ├── 02-algorithm.md    QMDECRYPTION.dll、TEA 派生、RC4/Map/KGM 表
│   ├── 03-toolchain.md    数据库 AES 分页解密、两条解密路径
│   └── 04-version-update.md
└── netease/               网易云 NCM
    ├── README.md
    ├── 01-file-format.md  keydata / meta / 封面 / 音频流
    ├── 02-algorithm.md    buildKeyBox、XOR 表、双 AES 链
    ├── 03-toolchain.md    解密脚本与验证方法
    └── 04-version-update.md
```

## 平台对比速览

| 维度 | QQ 音乐 (mflac/mgg) | 酷狗 (kgg) | 网易云 (ncm) |
|------|---------------------|------------|--------------|
| 文件头 | `fLaC` 加密 + 192B 尾部元数据 | 0x400B 头部(KGM_MAGIC + audio_hash) + 加密流 | `CTENFDAM` + keydata(128B) + meta + 封面 |
| 解密模块 | `QQMusicCommon.dll` → `CommonFunction.dll` | `QMDECRYPTION.dll`（**腾讯模块，被酷狗复用**） | `cloudmusic.dll`（固定 key 常量内嵌 .rdata） |
| 算法 | 定制 RC4 + 浮点随机偏移，512B 密钥 | **同源**：定制 RC4(Map/RC4 分支) + tan 随机，512B 密钥；**kgma 用 KGM 流表(三张 272B)** | buildKeyBox S-box + 256B XOR 表流密码 |
| 密钥来源 | 内嵌文件（尾部元数据） | **本地数据库** `KGMusicV3.db`（AES 分页）按 audio_hash 查 eKey；**kgma 例外**（密钥内嵌文件头 0x1C） | **内嵌文件**（keydata AES 解密派生） |
| 密钥派生 | 直接使用 | base64 → TEA(v1/v2) 派生 | keydata XOR 0x64 → AES(sCoreKey) → 取 `[17:]` |
| 离线解密 | ✅ 无需运行客户端 | ✅ 无需网络/客户端，但需本机数据库有该歌 eKey | ✅ 文件自带密钥，**换账号/换电脑均可** |
| 工具 | `tools/native/qqmusic/bin/QqmDec.exe`（C） | `tools/kugou.py`（Python）/ `tools/kugou_dll.py`（DLL） | `tools/netease.py`（Python） |

## 工具索引

| 工具 | 平台 | 说明 |
|------|------|------|
| `python -m tools decrypt` | 三平台 | **统一入口**：按扩展名分流，先跑它 |
| `tools/kugou.py` | 酷狗 | 纯 Python：解数据库 → 查 eKey → TEA 派生 → RC4/Map 流解密 |
| `tools/kugou_dll.py` | 酷狗 | ctypes 直调 `QMDECRYPTION.dll`，`CreateDecryption(eKey 原文)`，256/512 key 通吃、更快 |
| `tools/native/kugou/kgm_dec.c` | 酷狗 | kgma/kgm（crypto_ver 3）：密钥内嵌文件头 + 三张 272 字节表流解密，递归批量 |
| `tools/netease.py` | 网易云 | 解 ncm → 派生 key → 解 meta → 解密音频，四档音质通用 |
| `tools/native/qqmusic/QqmDec.c` | QQ 音乐 | 原生 C + `wmain`（Unicode 文件名），P/Invoke 调 `CommonFunction.dll` |
| `tools/native/qqmusic/QqmKeyDump.cs` | QQ 音乐 | 32 位 csc 编译，dump 解密器持有的实际密钥 |
| `tools/analysis/*.py` | QQ 音乐 | `disasm.py`（pefile+capstone）、`scan_dll.py`（导出/字符串）、`read_tail.py`（文件头尾）、`dump_key.py`（密钥 dump 思路） |

## 通用方法论（三平台共用）

1. **定位解密模块**：字符串扫描安装目录 DLL（找文件扩展名 `.mflac/.kgg/.ncm`、`Decrypt`、加密相关导出）
2. **文件结构分析**：对比头部/尾部，找 KGM/固定 magic、大小字段、哈希字段
3. **密钥管理是关键**：确认密钥是内嵌（QQ/网易云）还是外部分发（酷狗本地数据库/网络）
4. **算法识别**：`QMDECRYPTION.dll` 是腾讯 QQ 音乐模块 → 与 QQ 音乐算法同源（RC4 + tan 随机）
5. **固定 key 交叉验证**：搜索 DLL `.rdata` 中 16 字节固定常量（如网易云 `sCoreKey`/`sModifyKey`），
   用 AES S-box 等常量作锚点；字符串搜不到 magic 时先试"明文 XOR 常量"（网易云 meta 的 `RUPC` 假象）
6. **动态验证**：先写小脚本用已知明文反推或直接调 DLL，再离线实现
7. **交叉验证**：对照开源实现（unlock-music、KGG-Decryptor、ncmdump），剥离标签后逐字节对比

## 版本更新应对

- 平台更新后先看三件事：文件头 magic / `crypto_ver` / 解密 DLL 的导出符号有没有变
- 各子目录的 `04-version-update.md` 给了指纹速查表与逐步定位流程
- 手上没有新样本时，`python -m tools info <文件>` 能先告诉你"卡在哪一环"

> 免责声明：这里记录的是**本机已购内容**的格式互通方法，用于离线备份与播放器兼容。
> 请遵守各平台服务条款，不要传播受版权保护的音频，也不要把厂商的私有 DLL 提交进仓库。
