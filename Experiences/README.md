# 音频平台加密逆向经验库

> 沉淀腾讯系/酷狗系/网易系音乐客户端加密音频格式的逆向方法、算法结论与离线解密工具链。
> 目标：平台版本更新、加密方案调整后，能基于本库快速定位并更新破解方案。

## 目录结构

```
Experiences/
├── README.md          ← 本索引
├── QQMusic/           腾讯 QQ 音乐 mflac/mgg 解密
│   ├── README.md      核心结论、版本基线、踩坑
│   ├── 01~04 *.md     文件格式 / 算法逆向 / 工具链 / 版本应对
│   └── scripts/       反汇编、扫描、密钥 dump 等分析脚本
├── KGMusic/           酷狗音乐 KGG/kgma 解密
│   ├── README.md      核心结论、版本基线、踩坑
│   ├── 01~04 *.md     文件格式 / 算法逆向 / 工具链 / 版本应对
│   └── scripts/       KgDec.py（解密工具副本）
└── WYYMusic/          网易云音乐 NCM 解密
    ├── README.md      核心结论、版本基线、踩坑
    ├── 01~04 *.md     文件格式 / 算法逆向 / 工具链 / 版本应对
    └── scripts/       WYYDec.py（解密工具副本）
```

## 平台对比速览

| 维度 | QQ 音乐 (mflac/mgg) | 酷狗 (kgg) | 网易云 (ncm) |
|------|---------------------|------------|--------------|
| 文件头 | `fLaC` 加密 + 192B 尾部元数据 | 0x400B 头部(KGM_MAGIC + audio_hash) + 加密流 | `CTENFDAM` + keydata(128B) + meta + 封面 |
| 解密模块 | `QQMusicCommon.dll` → `CommonFunction.dll` | `QMDECRYPTION.dll`（**腾讯模块，被酷狗复用**） | `cloudmusic.dll`（固定 key 常量内嵌 .rdata） |
| 算法 | 定制 RC4 + 浮点随机偏移，512B 密钥 | **同源**：定制 RC4(Map/RC4 分支) + tan 随机，512B 密钥 | buildKeyBox S-box + 256B XOR 表流密码 |
| 密钥来源 | 内嵌文件（尾部元数据） | **本地数据库** `KGMusicV3.db`（AES 分页）按 audio_hash 查 eKey | **内嵌文件**（keydata AES 解密派生） |
| 密钥派生 | 直接使用 | base64 → TEA(v1/v2) 派生 | keydata XOR 0x64 → AES(sCoreKey) → 取 [17:] |
| 离线解密 | ✅ 无需运行客户端 | ✅ 无需网络/客户端，但需本机数据库有该歌 eKey | ✅ 文件自带密钥，**换账号/换电脑均可** |
| 工具 | `tools/QQMusic/QqmDec.exe`(C) | `tools/KgDec.py`(Python) | `tools/WYYDec.py`(Python) |

## 工具索引

| 工具 | 平台 | 说明 |
|------|------|------|
| `tools/QQMusic/QqmDec.exe` | QQ 音乐 | 原生 C，wmain Unicode，P/Invoke 调 CommonFunction.dll |
| `tools/QQMusic/QqmDec.c` | QQ 音乐 | 上述 exe 源码 |
| `tools/KgDec.py` | 酷狗 | 纯 Python，自动定位数据库→查 eKey→派生→解密，支持批量（归档副本 `Experiences/KGMusic/scripts/KgDec.py`） |
| `tools/WYYDec.py` | 网易云 | 纯 Python，解析 ncm→派生 key→解 meta→解密音频，四档音质通用（归档副本 `Experiences/WYYMusic/scripts/WYYDec.py`） |

## 通用方法论（三个库共用）

1. **定位解密模块**：字符串扫描安装目录 DLL（找文件扩展名 `.mflac/.kgg/.ncm`、`Decrypt`、加密相关导出）
2. **文件结构分析**：对比头部/尾部，找 KGM/固定 magic、大小字段、哈希字段
3. **密钥管理是关键**：确认密钥是内嵌（QQ/网易云）还是外部分发（酷狗本地数据库/网络）
4. **算法识别**：QMDECRYPTION.dll 是腾讯 QQ 音乐模块 → 与 QQ 音乐算法同源（RC4+tan 随机）
5. **固定 key 交叉验证**：搜索 DLL .rdata 中 16 字节固定常量（如网易云 sCoreKey/sModifyKey），
   用 AES S-box 等常量作锚点；字符串搜索不到 magic 时先尝试"明文 XOR 常量"（网易云 meta 的 `RUPC` 假象）
6. **动态验证**：先写小脚本用已知明文反推/直接调 DLL，再离线实现
7. **交叉验证**：对照 GitHub 开源实现（unlock-music、KGG-Decryptor、ncmdump），剥离标签后逐字节对比

## 版本更新应对

- 平台更新后先看：文件头 magic / crypto_ver / 解密 DLL 导出是否变化
- 各子库 `04-版本更新应对指南.md` 给出了指纹速查表与定位流程
