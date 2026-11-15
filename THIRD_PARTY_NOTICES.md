# 第三方来源与归属说明

本仓库的代码分三类，来源都写在这里。

## 1. 本仓库原创

- `tools/gui.py`、`tools/cli.py`、`tools/decrypt.py` —— 三平台调度、批量解密、统一命令行
- `tools/native/qqmusic/QqmDec.c`、`tools/native/qqmusic/QqmKeyDump.cs` —— QQ 音乐解密器（原生 C / C#）
- `tools/native/kugou/kgm_dec.c` —— kgma/kgm 流解密器（C）
- `tools/krc2lrc.py`、`tools/fix_ncm_lrc.py`、`tools/embed_lyric.py`、`tools/playlist_export.py` —— 歌词/歌单周边工具
- `docs/**` —— 逆向记录与分析结论

## 2. 移植/对照的开源实现（均为 MIT）

| 项目 | 用于 | 说明 |
| --- | --- | --- |
| [ncmdump](https://github.com/taurusxin/ncmdump)（v1.5.1） | `tools/netease.py` 的 ncm 解析与 keybox/XOR 表算法 | 已用 `cloudmusic.dll` 里的明文常量与 FLAC/MP3 帧逐字节交叉验证 |
| [KGG-Decryptor](https://github.com/Aaron-gx/KGG-Decryptor) | `tools/kugou.py` 的 RC4/Map 算法 | 与 `QMDECRYPTION.dll` 反汇编结论对照后重写 |
| AudioDecrypt（KGM.cpp） | `tools/native/kugou/kgm_dec.c` 的三张 272 字节表流解密 | kgma/kgm（crypto_ver 3）路径 |
| [unlock-music](https://github.com/ix64/unlock-music) | 交叉验证参考 | 仅作结果比对，未直接引用代码 |

## 3. 第三方专有二进制（**不随本仓库分发**）

| 文件 | 归属 | 用途 |
| --- | --- | --- |
| `QQMusicCommon.dll` | 腾讯（QQ 音乐） | 提供 `EncAndDesMediaFile` 类，QQ 音乐 mflac/mgg 解密的唯一公开入口 |
| `CommonFunction.dll` | 腾讯（QQ 音乐） | 上述 DLL 运行时加载的实际算法实现 |
| `QMDECRYPTION.dll` | 腾讯（被酷狗复用） | `tools/kugou_dll.py` 走的 C API 路径 |

这些文件属于各自厂商，**请不要提交到本仓库**（`.gitignore` 已忽略 `*.dll`）。
需要时从本机安装目录自行复制，见 `docs/` 对应平台的 `tool-native.md` / `03-toolchain.md`。

## 4. 样本音频

仓库不含任何音频样本：`.mflac/.mgg/.kgg/.kgma/.ncm` 与解出来的 `.flac/.mp3/.ogg`
都是受版权保护的内容，`.gitignore` 已整体忽略。自测请用自己的正版下载文件。
