# 用法：GUI 与命令行

三平台（QQ 音乐 mflac/mgg、酷狗 kgg/kgma、网易云 ncm）共用一套调度核心
`tools/decrypt.py`，外面包了两层壳：图形界面 `tools/gui.py` 与命令行 `tools/cli.py`。
两边行为一致，能干的活也一致，按场合挑一个。

## 0. 装依赖

```powershell
pip install -r requirements.txt           # 只有 cryptography，解密必需
pip install -r requirements-optional.txt  # 可选：拖拽、逆向分析脚本
```

QQ 音乐那条链路还要原生件，见下面「三平台前置条件」。

## 1. 命令行（推荐给批量/脚本）

```powershell
python -m tools info    samples -r                  # 先体检：哪些文件能解、走哪条路
python -m tools decrypt samples -r -o .\decoded     # 批量解密
python -m tools decrypt song.mflac -o out.flac      # 单文件
python -m tools decrypt samples --only netease      # 只处理网易云
python -m tools --version
```

输出规则：

- 输入是**文件** → 默认输出到同目录，同名换扩展名（`a.ncm` → `a.flac/a.mp3`，`a.mgg` → `a.ogg`）
- 输入是**文件夹** → 默认输出到父目录下 `文件夹名_decoded`，保持子目录结构
- 指定 `-o` → 全部落到该目录（保留相对路径）
- 退出码：`0` 全成、`1` 有失败、`2` 用法/环境问题（脚本里可以直接判）

各平台还能单独跑（等价于剥掉调度层）：

```powershell
python tools\netease.py   samples\netease  decoded\netease -r
python tools\kugou.py     samples\kugou   decoded\kugou --db D:\path\KGMusicV3.db
python tools\kugou_dll.py samples\kugou   decoded\kugou --dll D:\KGMusic\20.1.41.27870\QMDECRYPTION.dll
tools\native\kugou\bin\kgm_dec.exe samples\kugou decoded\kgm
tools\native\qqmusic\bin\QqmDec.exe samples\qqmusic decoded\qqmusic
```

## 2. 图形界面

```powershell
python tools\gui.py                       # 双击也行
python tools\gui.py "D:\Temp\WYY_caches"  # 带路径则自动填入输入框
```

| 控件 | 说明 |
|------|------|
| 输入框 | 文件或文件夹，可多个；**支持直接粘贴路径字符串**（`D:\Temp\WYY_caches`，多个用换行/分号分隔） |
| 选择文件 / 选择文件夹 | 弹窗多选 |
| 输出框 | 留空=自动；填文件夹=输出到该文件夹；选"输出文件"=写到指定文件（仅单个输入时生效） |
| 递归处理子目录 | 文件夹输入时含子目录并保持目录结构 |
| 完成后提示 | 提示音 + 弹窗 |
| 进度条 / 取消 | 后台线程解密，界面不卡，可中断 |
| 拖拽 | 把文件/文件夹直接拖进窗口（需 `tkinterdnd2`） |
| 记住路径 | 关闭时自动存到 `~/.tunelock_gui.json`，下次打开恢复 |

解出的 `*_decoded` 目录不会被再次递归扫描（自动跳过），可以反复跑。

## 3. 三平台前置条件

| 平台 | 解密方式 | 需要什么 |
|------|----------|----------|
| 网易云 ncm | 内置 `tools/netease.py` | 无（密钥内嵌文件），只要 `cryptography` |
| 酷狗 kgg | 内置 `tools/kugou.py` | 本机 `%APPDATA%\KuGou8\KGMusicV3.db` 含该歌 eKey（酷狗能播的歌才有） |
| 酷狗 kgma/kgm | `kgm_dec.exe` | 编译好的 `tools/native/kugou/bin/kgm_dec.exe`（`bash build/build.sh kgm`） |
| QQ 音乐 mflac/mgg | subprocess 调 `QqmDec.exe` | ① 编好的 `tools/native/qqmusic/bin/QqmDec.exe`；② `CommonFunction.dll` 与 exe **同目录**；③ 本机 QQ 音乐安装提供 `QQMusicCommon.dll`（或设 `QQMUSIC_DIR`） |

`python -m tools info` 会逐条报缺什么，缺件时的提示就是按上表来的。

## 4. 环境变量

| 变量 | 作用 |
|------|------|
| `QQMUSIC_DIR` | QQ 音乐安装目录（找 `QQMusicCommon.dll`） |
| `QQM_EXE` | 指定 `QqmDec.exe` 路径 |
| `KG_DB` | 指定 `KGMusicV3.db` |
| `KG_DLL` | 指定 `QMDECRYPTION.dll` |
| `FFMPEG` | 歌词内嵌用的 `ffmpeg.exe` |
| `KUGOU_LYRIC_DIR` | `tools/krc2lrc.py` 默认扫描目录 |

## 5. 性能说明

- 网易云 / 酷狗纯 Python 路径：解一个文件基本是 IO 时间
- 酷狗数据库只解一次（批量时不重复解密 5–10MB 的库）
- QQ 音乐走子进程，每次启动有约 5 秒固定开销（腾讯 DLL 初始化/清理，换语言也消不掉），
  批量文件越多摊薄越划算 —— 所以**别一个一个传，传目录**
