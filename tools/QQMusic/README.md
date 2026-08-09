# QQ音乐 mflac 解密工具

## 背景

QQ 音乐下载的 VIP 歌曲以专属加密格式保存：`.mflac`（加密的 FLAC）和 `.mgg`（加密的 Ogg）。
本工具通过直接调用 QQ 音乐自带的 `QQMusicCommon.dll` 中的 `EncAndDesMediaFile` 类完成离线解密，
无需运行 QQ 音乐客户端。

## 原理（逆向分析结论）

### 1. 文件结构

`musics` 目录中的 `.mflac` 文件由两部分组成：

```
[加密的 FLAC 音频数据] + [192 字节下载器附加的元数据块]
```

192 字节附加块内容：
- `002P5kP80d88Vp` —— 歌曲 ID（UTF-16LE）
- `F0M0000Cc0LP1jd0bj.mflac` —— 下载时 P2P 缓存文件名（UTF-16LE）
- `81 6c 96 aa` + `c0 00 00 00` + `01 00 00 00` + `musicex\0` —— 尾部标记

解密后这 192 字节被去除，输出为标准 FLAC（头部 `fLaC`）。

### 2. 解密算法（CommonFunction.dll）

加密/解密核心位于 `QQMusicCommon.dll` 的 `EncAndDesMediaFile` 类，实际算法在
`CommonFunction.dll`（通过 `LoadLibraryW("CommonFunction.dll")` 动态加载）：

- **导出序号 3**：创建解密器对象（vtable `0x1000ea2c`，大小 0x30）
- **导出序号 8/9**：构造/释放密钥对象
- **vtable slot[1]（RVA 0x96B0）**：`SetKey(key, keylen)`，密钥是 512 字节的 base64 字符串
- **vtable slot[4]（RVA 0x9A20）→ slot[3]（RVA 0x98A0）**：解密入口
- **RVA 0x9A60**：RC4 变体密钥调度（KSA），S-box 长度 = 密钥字节数
- **RVA 0x9B40 / 0x9CB0**：分组解密（PRGA），每 0x1400 字节一块，
  用 `[obj+0x28]`（密钥字节累积乘积）做浮点随机偏移生成密钥流，逐字节 XOR

解密本质是**定制版 RC4 流密码 + 浮点随机偏移**，密钥由文件派生（512 字节 base64 字符串）。

## 使用方法

### 编译（可选，已提供 exe）

原生 C 版本（推荐，启动快、无 .NET 依赖）：

```bash
# 需要 32 位 MinGW（msys2 的 mingw32 环境）
gcc -O2 -o QqmDec.exe QqmDec.c -lkernel32 -luser32
```

> 说明：`QQMusicCommon.dll` 是 32 位 DLL，必须用 32 位编译器。
> 已提供预编译的 `QqmDec.exe`，直接使用即可。

### 运行

```powershell
# 解密单个文件
QqmDec.exe <输入.mflac> <输出.flac>

# 批量解密目录下所有 mflac/mgg
QqmDec.exe <输入目录> <输出目录>
```

### 性能说明

- 解密本身约 0.6 秒/文件
- 每次进程启动有约 5 秒固定开销，来自 QQ 音乐 `QQMusicCommon.dll`
  加载/卸载（Open 初始化解密器后的 DLL 清理，无法避免）
- **建议用批量模式**：一次启动处理多个文件，固定开销只付一次
  （2 个文件约 6.3 秒，与 1 个文件的 5.7 秒接近）

依赖：运行时自动从 QQ 音乐安装目录（默认 `E:\QQMusic`，若 exe 与
`QQMusicCommon.dll` 同目录则用该目录）加载解密所需 DLL。

## 验证结果

| 输入 | 输出 | 大小 | 头 4 字节 |
|------|------|------|-----------|
| Michael Jackson - Billie Jean.mflac | Billie Jean.flac | 68,107,843 | `66 4C 61 43` (fLaC) |
| Michael Jackson - You Are Not Alone.mflac | You Are Not Alone.flac | 74,023,759 | `66 4C 61 43` (fLaC) |
