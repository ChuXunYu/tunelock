# 更新日志

版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## 2.0.0 — 2026-11-15

仓库从 `QQMusic_Reserve` 更名为 **TuneLock**，并做了一次彻底的结构整理。
命令行入口与目录路径全部变化，按语义化版本属破坏性升级。

### 变更

- **仓库更名**：`QQMusic_Reserve` → `tunelock`（原名与内容不符：项目做的是三平台解密＋逆向笔记，不是"预约"）
- **目录重构**
  - `Experiences/` → `docs/`，文档统一改 ASCII 文件名（`01-file-format.md` …）
  - `tools/*.py` 统一 snake_case：`KgDec.py` → `kugou.py`、`WYYDec.py` → `netease.py`、`DecryptGUI.py` → `gui.py`…
  - 原生源码集中到 `tools/native/{qqmusic,kugou}/`，产物放各自的 `bin/`
  - 逆向分析脚本集中到 `tools/analysis/`
- **新增统一入口**：`tools/decrypt.py`（GUI 与 CLI 共用的调度核心）、`tools/cli.py`、`python -m tools`
- **补齐工程文件**：`README.md`、`LICENSE`（MIT）、`THIRD_PARTY_NOTICES.md`、`CHANGELOG.md`、
  `requirements*.txt`、`.gitattributes`、`.editorconfig`、`build/` 编译脚本、`samples/`
- **去重**：删除 `Experiences/*/scripts/` 下的四份工具副本（`KgDec.py`、`KgDec_dll.py`、`WYYDec.py`、`QqmDec.c`），全库只留一份
- **不再入库**：腾讯私有 `CommonFunction.dll`、所有音频样本、编译产物之外的第三方库

### 优化

- 硬编码路径全部改为可探测 + 环境变量覆盖：`QQMUSIC_DIR`、`QQMUSIC_DLL`、`QQ_DLL`、`KG_DB`、`KG_DLL`、`FFMPEG`、`KUGOU_LYRIC_DIR`
- `tools/kugou_dll.py` 复用 `tools/kugou.py` 的数据库解密与 eKey 派生（原本两份 90 行重复实现，容易漂移）
- 酷狗临时明文数据库改为 `mkstemp` + 用完即删（原先固定文件名，会留在 `%TEMP%`）
- 所有 `open()` 改为 `with`，异常路径不再泄漏句柄
- `tools/kugou.py`、`tools/netease.py` 增加 `-r/--recursive`
- `tools/cli.py` 在 Windows 控制台强制 UTF-8 输出，中文不再乱码
- QQ 解密链缺件时给出具体缺什么（exe / CommonFunction.dll / QQMusicCommon.dll），不再只丢一个 `Open failed`
- GUI 配置文件改名 `.tunelock_gui.json`（旧的 `.musdec_gui.json` 不再使用）

### 验证

- `python -m tools decrypt` 实测：网易云 ncm 4/4、QQ 音乐 mflac 1/1 成功，输出与 `musics/*_decoded` 参考文件逐字节一致
- 酷狗 kgg 3/3 报"本机数据库无该歌 eKey"（样本下载于 2026-08，eKey 已被轮换，非代码问题）
- `python -m py_compile` 全绿

## 1.0.0 — 2026-08-10

首个成型版本，三平台解密链各自打通：

- QQ 音乐 mflac/mgg：`EncAndDesMediaFile` 路径（C# → 原生 C + wmain Unicode），批量模式
- 酷狗 kgg：`QMDECRYPTION.dll` 直调（推荐）与纯 Python 双路径；kgma/kgm 走三张 272 字节表流解密
- 网易云 ncm：keydata/meta 双 AES 链 + buildKeyBox/XOR 表，四档音质通用
- 三平台统一 GUI（拖拽、批量、递归、取消、记住路径）
- 歌词/歌单周边：KRC → LRC、网易云 LRC 修复、歌词内嵌、QQ 歌单导出
- 逆向经验库：每平台 4 篇（文件格式 / 算法 / 工具链 / 版本更新应对）
