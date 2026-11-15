# QQ 音乐 mflac/mgg 解密逆向经验库

> 目标：沉淀 QQ 音乐音频加密格式的逆向分析方法、算法结论与工具链，
> 使将来 QQ 音乐版本更新、加密算法调整后，能基于本库快速定位并更新破解方案。

## 版本基线

| 项目 | 值 |
|------|-----|
| 分析日期 | 2026-08-09 |
| QQ 音乐版本 | 2231.3575（日志 `QQMusic(2231.3575)20260809041605.log`） |
| 安装目录 | `E:\QQMusic` |
| 缓存目录 | `D:\Temp\QQ_music_caches\`（注册表 `HKCU\Software\Tencent\QQMusic\LogConfig\CACHEPATH`） |
| 样本文件 | `samples\Michael Jackson - Billie Jean.mflac` 等 |

## 核心结论速览

1. **`.mflac` 文件 = 加密 FLAC 数据 + 192 字节下载器附加元数据块**
   - 元数据块含：歌曲 ID（UTF-16LE）、P2P 缓存文件名（UTF-16LE）、`musicex\0` 尾部标记
   - 解密后元数据块被去除，输出标准 FLAC（头 `fLaC`）
2. **解密核心不在主 DLL**，而在 `QQMusicCommon.dll` 的 `EncAndDesMediaFile` 类
3. **实际算法位于 `CommonFunction.dll`**（运行时通过 `LoadLibraryW` 动态加载），
   导出序号 3/8/9 构造解密器
4. **算法是定制版 RC4 流密码 + 浮点随机偏移**，密钥 512 字节 base64 字符串
5. **离线解密 = 直接 P/Invoke 调用 DLL 类方法**，无需运行 QQ 音乐
6. **mgg 与 mflac 同算法**：HQ(`_H.mgg`)、标准(`_L.mgg`)、mflac 全部用同一
   `EncAndDesMediaFile` 路径解密，输出 Ogg（头 `OggS`）

## 重要踩坑（务必先读）

| 坑 | 现象 | 真相 |
|----|------|------|
| mgg Open 失败 | 对 `_L.mgg` 报 Open=0、EncType=0 | **不是格式问题**，是韩文/中文文件名在 PowerShell→argv 传递时被损坏成 `?`，DLL 找不到文件 |
| GetEncType 按扩展名 | 看似按文件头判断 | 实际按**扩展名**匹配（`.mflac`/`.mgg`/`.mmp4` → EncType=2） |
| msys2 swprintf | 拼接路径只剩首字符 | MinGW 的 `swprintf` 是 **POSIX 风格（无 size 参数）**，Windows 风格需用 `_snwprintf` |

## 工具链演进（重要经验）

| 阶段 | 方案 | 结果 |
|------|------|------|
| v1 | C#（32 位 csc，`CallingConvention.ThisCall`） | 可用，单文件 7s，不支持 Unicode 文件名 |
| v2 | 原生 C（msys2 mingw32 i686 gcc，`__thiscall`） | 单文件 5.7s，无运行时依赖 |
| v3 | 原生 C + **wmain 宽字符** | **最终采用**，支持中文/韩文文件名 |

**性能结论**：解密本身只要 0.6s；约 5 秒是 `QQMusicCommon.dll` 在 Open 后
进程退出时的资源清理开销（腾讯 DLL 固有，换语言无法消除）。
建议用**批量模式**一次处理多文件摊薄固定开销（详见 `03-toolchain.md` §6）。

## 文档索引

| 文件 | 内容 |
|------|------|
| `01-file-format.md` | mflac/mgg 文件结构、尾部元数据块、质量等级、缓存目录定位 |
| `02-algorithm.md` | EncAndDesMediaFile 类、GetEncType 扩展名判定、CommonFunction.dll 算法、IAT/关键偏移 |
| `03-toolchain.md` | C 原生方案、msys2 工具链、`__thiscall`、wmain Unicode、DLL 搜索坑、性能定位 |
| `04-version-update.md` | QQ 音乐更新后如何用本库快速定位新算法 |
| `tools/analysis/` | 可复用分析脚本（反汇编、字符串扫描、密钥 dump、文件头尾） |

## 关键文件

- `tools/analysis/disasm.py` — pefile+capstone 反汇编辅助
- `tools/analysis/scan_dll.py` — DLL 导出符号/字符串扫描
- `tools/analysis/read_tail.py` — mflac/mgg 文件头尾结构分析
- `tools/analysis/dump_key.py` — 密钥 dump 原理说明（详见 02 文档）
- `tools/native/qqmusic/QqmKeyDump.cs` — 密钥 dump 工具源码（32 位 csc 编译）
- `tools/native/qqmusic/QqmDec.c` — 离线解密工具源码（tools/native/qqmusic/bin/QqmDec.exe 的源，原生 C，wmain Unicode）
