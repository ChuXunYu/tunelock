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
| 样本文件 | `musics\Michael Jackson - Billie Jean.mflac` 等 |

## 核心结论速览

1. **`.mflac` 文件 = 加密 FLAC 数据 + 192 字节下载器附加元数据块**
   - 元数据块含：歌曲 ID（UTF-16LE）、P2P 缓存文件名（UTF-16LE）、`musicex\0` 尾部标记
   - 解密后元数据块被去除，输出标准 FLAC（头 `fLaC`）
2. **解密核心不在主 DLL**，而在 `QQMusicCommon.dll` 的 `EncAndDesMediaFile` 类
3. **实际算法位于 `CommonFunction.dll`**（运行时通过 `LoadLibraryW` 动态加载），
   导出序号 3/8/9 构造解密器
4. **算法是定制版 RC4 流密码 + 浮点随机偏移**，密钥 512 字节 base64 字符串
5. **离线解密 = 直接 P/Invoke 调用 DLL 类方法**，无需运行 QQ 音乐

## 文档索引

| 文件 | 内容 |
|------|------|
| `01-文件格式分析.md` | mflac 文件结构、尾部元数据块、缓存目录定位 |
| `02-算法逆向记录.md` | EncAndDesMediaFile 类、CommonFunction.dll 算法、IAT/关键偏移 |
| `03-工具链构建.md` | C# 离线调用方案、32 位 csc、DLL 搜索顺序坑 |
| `04-版本更新应对指南.md` | QQ 音乐更新后如何用本库快速定位新算法 |
| `scripts/` | 可复用分析脚本（反汇编、字符串扫描、密钥 dump） |

## 关键文件

- `scripts/disasm.py` — pefile+capstone 反汇编辅助
- `scripts/scan_dll.py` — DLL 导出符号/字符串扫描
- `scripts/read_tail.py` — mflac 文件头尾结构分析
- `scripts/dump_key.py` — 密钥 dump 原理说明（详见 02 文档）
- `scripts/QqmKeyDump.cs` — 密钥 dump 工具源码（32 位 csc 编译）
- `scripts/QqmDec.cs` — 离线解密工具源码（tools/QqmDec.exe 的源）
