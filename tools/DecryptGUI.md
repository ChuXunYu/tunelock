# DecryptGUI - 三平台加密音乐统一解密 GUI

一个图形界面工具，统一解密 **QQ音乐 (mflac/mgg)**、**酷狗 (kgg)**、**网易云 (ncm)** 三种加密音频格式。

## 运行

```powershell
pip install cryptography tkinterdnd2   # 首次
python tools\DecryptGUI.py
```

直接双击或 `python DecryptGUI.py <路径...>`（带路径则自动填入输入框）。

## 界面功能

| 控件 | 说明 |
|------|------|
| 输入框 | 文件或文件夹，可多个；**支持直接粘贴路径字符串**（如 `D:\Temp\WYY_caches`），多个用换行/分号分隔 |
| 选择文件 / 选择文件夹 | 弹窗多选 |
| 输出框 | 留空=自动（见下）；填文件夹=输出到该文件夹；选"输出文件"=写到指定文件（单个输入时生效） |
| 递归处理子目录 | 文件夹输入时含子目录并保持目录结构 |
| 完成后提示 | 提示音 + 弹窗 |
| 进度条 / 取消 | 后台线程解密，界面不卡，可中断（正在跑的 QQ 子进程也会终止） |
| 拖拽 | 把文件/文件夹直接拖进窗口 |
| 记住路径 | 关闭自动保存输入/输出/选项，下次打开恢复（`~/.musdec_gui.json`） |

## 输出规则

- **输入是文件** → 默认输出到同目录，同名换扩展名（`a.ncm` → `a.flac/a.mp3`，`a.mgg` → `a.ogg`，`a.mflac` → `a.flac`）
- **输入是文件夹** → 默认输出到父目录下 `文件夹名_decoded`（`D:\Temp\WYY_caches` → `D:\Temp\WYY_caches_decoded`），保持子目录结构
- 输出框填了目录 → 所有结果输出到该目录（保留相对路径）
- 网易云日志会附带歌名/码率元数据

## 三平台依赖

| 平台 | 解密方式 | 前置条件 |
|------|----------|----------|
| 网易云 ncm | 内置 WYYDec.py | 无，密钥内嵌文件 |
| 酷狗 kgg | 内置 KgDec.py | 本机 `%APPDATA%\KuGou8\KGMusicV3.db` 含该歌 eKey（酷狗能播的歌即可） |
| QQ 音乐 mflac/mgg | subprocess 调 `tools/QQMusic/QqmDec.exe` | `QQMusicCommon.dll`（exe 同目录或 `E:\QQMusic`，自动探测） |

> 酷狗 `KGMusicV3.db` 只读一次后复用（批量不重复解密数据库）；QQ 每次启动子进程有约 5s 固定开销，批量文件越多摊薄越划算。

## 说明

- 输出文件在对应 `_decoded` 目录，与输入互不影响，可反复运行。
- 解出的 `_decoded` 目录不会再被递归扫描（自动跳过 `*_decoded`）。
