# TuneLock

> 三平台加密音乐解密工具链 + 一份可复用的逆向笔记。
> QQ 音乐 `mflac/mgg`、酷狗 `kgg/kgma/kgm`、网易云 `ncm` → 直接拿到 `flac/mp3/ogg`。

![platform](https://img.shields.io/badge/platform-Windows-0078d4)
![python](https://img.shields.io/badge/python-3.9%2B-3776ab)
![license](https://img.shields.io/badge/license-MIT-green)

```
mflac/mgg ─┐
kgg/kgma  ─┼─►  tools/decrypt.py  ─►  flac / mp3 / ogg
ncm       ─┘        (统一调度)
```

## 平台支持

| 平台 | 格式 | 解密依据 | 需要本机客户端？ | 工具 |
| --- | --- | --- | --- | --- |
| QQ 音乐 | `.mflac` `.mgg` | 文件尾部 192B 元数据里的 512B 密钥，调 `CommonFunction.dll` 解 | 需要安装目录里的两个 DLL | `QqmDec.exe`（原生 C） |
| 酷狗 | `.kgg` | 本机数据库 `KGMusicV3.db` 按 `audio_hash` 查 eKey → TEA 派生 → RC4/Map | 需要该歌的 eKey（能播就能解） | `tools/kugou.py` / `tools/kugou_dll.py` |
| 酷狗 | `.kgma` `.kgm` | 密钥内嵌文件头 0x1C，三张 272B 表流解密 | 不需要 | `tools/native/kugou/kgm_dec.c` |
| 网易云 | `.ncm` | keydata ⇒ `sCoreKey` AES 派生的 S-box + XOR 表 | 不需要（换机也能解） | `tools/netease.py` |

顺带还有：酷狗 `krc` 歌词转 `lrc`、网易云 `lrc` 里混进的 JSON 逐字歌词修复、歌词内嵌进音频标签、QQ 歌单导出。

## 为什么值得看

- **三套方案真的跑通了，不是伪代码**：每个平台都有实测数据和逐字节验证（见文末）
- **一份代码两种用法**：`python -m tools`（批量/脚本）与 `tools/gui.py`（拖拽/进度/取消）共用同一个调度核心，不存在"GUI 能解 CLI 不能解"
- **逆向过程写下来了**：每平台 4 篇（文件格式 / 算法 / 工具链 / 版本更新后怎么重新定位），换版本时照着走，不用从零再来
- **不靠猜**：算法结论都能追到具体 DLL 的 RVA、导出序号或固定常量，见 [`docs/`](docs/README.md)
- **干净**：仓库里没有音频、没有厂商私有 DLL、没有编译产物之外的二进制

## 快速开始

```powershell
git clone https://github.com/ChuXunYu/tunelock.git
cd tunelock
pip install -r requirements.txt          # 只有 cryptography

python -m tools info    samples -r      # 先体检：能不能解、走哪条路
python -m tools decrypt samples -r -o .\decoded
```

图形界面：

```powershell
python tools\gui.py
```

QQ 音乐那条链路要先准备原生件（详见 [docs/gui.md](docs/gui.md#3-三平台前置条件)）：

```powershell
pwsh -File build\build.ps1                 # 编 QqmDec.exe（需 32 位 gcc）+ kgm_dec.exe
# 然后把 QQ 音乐安装目录里的这两个 DLL 复制到 tools\native\qqmusic\bin\
#   QQMusicCommon.dll
#   CommonFunction.dll      ← 必须在 exe 同目录
```

## 目录结构

```
tunelock/
├── tools/
│   ├── decrypt.py          统一调度（GUI/CLI 共用）
│   ├── cli.py              python -m tools decrypt | info
│   ├── gui.py              图形界面
│   ├── netease.py          网易云 ncm
│   ├── kugou.py            酷狗 kgg（纯 Python）
│   ├── kugou_dll.py        酷狗 kgg（直调 QMDECRYPTION.dll）
│   ├── krc2lrc.py          酷狗加密歌词 .krc → .lrc
│   ├── fix_ncm_lrc.py      网易云 lrc 里的 JSON 逐字歌词 → 标准 LRC
│   ├── embed_lyric.py      把 .lrc 无损写进音频标签（ffmpeg）
│   ├── playlist_export.py  QQ 歌单导出（公开 API，无需登录）
│   ├── native/
│   │   ├── qqmusic/        QqmDec.c（解密器）、QqmKeyDump.cs（密钥 dump）、bin/
│   │   └── kugou/          kgm_dec.c（kgma/kgm 解密器）、bin/
│   └── analysis/           disasm.py / scan_dll.py / read_tail.py / dump_key.py
├── docs/                   逆向笔记（qqmusic / kugou / netease 各 4 篇 + gui.md）
├── build/                  build.ps1 / build.sh
├── samples/                样本放这里（.gitignore 已忽略，仓库里只有说明）
├── requirements.txt        核心依赖
└── requirements-optional.txt  GUI 拖拽 + 分析脚本
```

## 实测验证

| 项目 | 样本 | 结果 |
| --- | --- | --- |
| 网易云 ncm | 4 个（FLAC 24bit / FLAC 16bit / MP3 320k / MP3 128k） | 4/4 成功；解码后音频流 MD5 与历史产物**完全一致**（仅少了后来内嵌的歌词标签） |
| QQ 音乐 mflac | `Syn Cole _ Nevve - Sway.mflac` | 25,922,613 → 25,922,421 字节，正好剥掉 192 字节尾部 |
| 酷狗 kgma | `Daniel Powter - Free Loop.kgma` | 23,047,198 → 23,046,174 字节，输出头 `66 4C 61 43`（`fLaC`） |
| 酷狗 kgg | 3 个样本 | 报「本机数据库无该歌 eKey」：样本是 2026-08 下载的，eKey 已被轮换，属预期 |

想自己复现：把正版下载的加密文件丢进 `samples/<平台>/`，跑 `python -m tools info samples -r` 看判定，再 `decrypt`。

## 环境变量

| 变量 | 作用 |
| --- | --- |
| `QQMUSIC_DIR` | QQ 音乐安装目录（找 `QQMusicCommon.dll`） |
| `QQM_EXE` | 指定 `QqmDec.exe` |
| `KG_DB` | 指定 `KGMusicV3.db` |
| `KG_DLL` | 指定 `QMDECRYPTION.dll` |
| `FFMPEG` | 歌词内嵌用的 `ffmpeg.exe` |
| `KUGOU_LYRIC_DIR` | `krc2lrc.py` 默认扫描目录 |

## 逆向笔记

| 平台 | 入口 | 亮点 |
| --- | --- | --- |
| QQ 音乐 | [docs/qqmusic](docs/qqmusic/README.md) | `EncAndDesMediaFile` 类、导出序号 3/8/9、KSA `RVA 0x9A60`、每 0x1400 字节一块的浮点随机偏移；`msys2 swprintf` 与 Unicode 文件名的坑 |
| 酷狗 | [docs/kugou](docs/kugou/README.md) | 数据库 AES-128-CBC 分页（第 1 页特殊）、`CreateDecryption` 要吃 **eKey base64 原文**、kgma 走三张 272B 表 |
| 网易云 | [docs/netease](docs/netease/README.md) | `RUPC` 只是 `"163 " ^ 0x63`、keybox 前 16 字节恒等是 AES-ECB 的指纹、四档音质同算法 |

## 边界

- 只处理**你自己已购买/已下载**的内容，用于离线备份与播放器兼容；不提供任何下载或绕过付费的功能
- 仓库不含音频样本，也不含厂商私有 DLL（`.gitignore` 已忽略），需要时从自己的安装目录自备
- 算法与接口随客户端更新会变，`04-version-update.md` 就是为这天准备的

## 致谢与许可

算法部分对照/移植了几个开源实现（ncmdump、KGG-Decryptor、AudioDecrypt），归属见
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。本项目采用 [MIT](LICENSE)。
