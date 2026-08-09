# 02 - 算法逆向记录

## 1. 逆向入口定位（方法论）

### 1.1 从字符串/导出符号入手

在 `E:\QQMusic` 所有 DLL/EXE 中搜索关键词：

| 关键词 | 命中位置 | 意义 |
|--------|---------|------|
| `musicex` | `QQMusicCommon.dll` | 尾部标记，但实为网络配置 |
| `.mflac` | `QMNetwork.dll` | 下载相关 |
| `MusicEx` | `QQMusic.dll`, `QQMusicExternal.exe` | 无关 |
| `EncAndDesMediaFile` | `QQMusicCommon.dll` 导出表 | **核心类！** |
| `CEncryptFile` | `QQMusicCommon.dll` | 配置文件加密，与音频无关 |

**关键：查看导出表**（`??0EncAndDesMediaFile@@QAE@XZ` 等）。

```python
import pefile
pe = pefile.PE(r'E:\QQMusic\QQMusicCommon.dll')
pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_EXPORT']])
for exp in pe.DIRECTORY_ENTRY_EXPORT.symbols:
    n = exp.name.decode('latin1', 'replace') if exp.name else ''
    if 'MediaFile' in n or 'EncAndDes' in n:
        print(hex(exp.address), n)
```

### 1.2 类方法清单（本版本 RVA）

| 导出（mangled） | RVA | 用途 |
|-----------------|-----|------|
| `??0EncAndDesMediaFile@@QAE@XZ` | 0x12F0B | 构造函数 |
| `?Open@EncAndDesMediaFile@@QAE_NPB_W_N1@Z` | 0x1369D | 打开(path,dealDecrypt,?) |
| `?Open@EncAndDesMediaFile@@QAE_NPB_WKKK@Z` | 0x12FB5 | 底层打开(4参) |
| `?GetEncType@EncAndDesMediaFile@@SA?AW4EncType@1@PB_W@Z` | 0x13BB8 | 识别加密类型(静态) |
| `?GetSize@EncAndDesMediaFile@@QAEKXZ` | 0x13720 | 解密后大小 |
| `?Read@EncAndDesMediaFile@@QAEKPAEK_J@Z` | 0x137B5 | 读取+解密 |
| `?ReadEncKey@EncAndDesMediaFile@@AAEHXZ` | 0x133F2 | 读密钥(私有) |
| `?SetDealDecrypt@EncAndDesMediaFile@@QAEX_N@Z` | 0x12FA8 | 设置解密开关 |
| `?SetEkey@EncAndDesMediaFile@@QAE_NPBDH@Z` | 0x13643 | 设置密钥 |
| `?Close@EncAndDesMediaFile@@QAEXXZ` | 0x136EF | 关闭 |
| `?Seek@EncAndDesMediaFile@@QAE_N_JK@Z` | 0x1399C | 定位 |

### 1.3 Open 内部流程（RVA 0x12FB5 起）

```
CreateFileW(path)                       ; 0x100b50d4
GetFileSize                             ; 0x100b50d8
if [this+8](SetDealDecrypt) == 1:
    GetEncType(path)  -> 若 == 2 (mflac/mgg) 继续
    [this+0x18] = LoadLibraryW("CommonFunction.dll")   ; 0x100b50dc
    GetProcAddress(hMod, (char*)3)      ; 创建解密器对象
    [this+0x14] = 解密器对象
    ReadEncKey()                        ; 读密钥
```

### 1.4 ReadEncKey 流程（RVA 0x133F2）

```
SetFilePointer(hFile, -4, 0, FILE_END)  ; 0x100b50e0
ReadFile(4 bytes)  ->  keylen           ; 0x100b50e4
if !(5 <= keylen <= 0x3ff): return 0
memset(buf, 0, 0x400)
SetFilePointer(hFile, -4-keylen, 0, FILE_END)
ReadFile(buf, keylen)
GetProcAddress(hMod, (char*)8)   ; 构造 key 对象
key_obj->vtable[0](buf, keylen)  ; 设置 key
[this+0x14]->vtable[8](key_obj)  ; 传给解密器
[this+0x1c] = keylen + 4
```

## 2. 解密算法核心（CommonFunction.dll）

### 2.1 模块定位

`CommonFunction.dll` 导出全部无名字函数，用序号访问：

| 序号 | RVA | 用途 |
|------|-----|------|
| 3 | 0x1650 | 创建解密器对象（vtable=0x1000ea2c, 大小0x30） |
| 7 | 0x15E0 | 释放对象 |
| 8 | 0x17A0 | 构造 key 对象 |
| 9 | 0x17E0 | 释放 key 对象 |

### 2.2 解密器 vtable（0x1000ea2c）

| slot | RVA | 用途 |
|------|-----|------|
| [0] | 0x96A0 | no-op |
| [1] | 0x96B0 | SetKey(key, keylen) |
| [2] | 0x97A0 | （未深入） |
| [3] | 0x98A0 | Decrypt 入口（分发） |
| [4] | 0x9A20 | Decrypt 包装 → 调 slot[3] |

### 2.3 密钥调度 KSA（RVA 0x9A60）

伪代码（S-box 长度 = keylen）：
```
[this+0x2c] = malloc(keylen)
S[i] = i  for i in 0..keylen-1
j = 0
for i in 0..keylen-1:
    j = (j + S[i] + key[i]) % keylen
    swap(S[i], S[j])

# 计算 [this+0x28]：密钥字节的累积乘积
acc = 1
for b in key:
    if b == 0: continue
    p = b * acc
    if p == 0: break
    if p <= acc: break
    acc = p
[this+0x28] = acc
```

### 2.4 分组解密 PRGA（RVA 0x9B40 / 0x9CB0）

- 大文件（keylen > 0x12c）走 0x9CB0，按 0x1400 字节一块调用 0x9B40
- 每块用浮点运算 + `[this+0x28]` 生成随机偏移作为密钥流起点
- 密钥流生成（RC4 变体）：
```
i = (i+1) % keylen
j = (j + S[i]) % keylen
swap(S[i], S[j])
keystream = S[(S[i] + S[j]) % keylen]
out[k] = data[k] ^ keystream
```

### 2.5 编译器运行时辅助函数（识别即可，不必逆向）

| 地址 | 对应 CRT |
|------|---------|
| 0x1000c820 | __aullrem（64位取模） |
| 0x1000c770 | __allmul（64位乘法） |
| 0x1000cbe0 | __ltod3（int64→double） |
| 0x1000cac0 | _ftol2（double→int64） |
| 0x1000c7b0 | __aulldiv（64位除法） |
| 0x1000c6dc / 0x1000c6e2 | memset / memcpy |
| 0x1000bd11 / 0x1000bd0c | malloc / free |
| 常量 0x1000eb18 | 100.0 |
| 常量 0x1000eb40 | [0, 4294967296]（int32→double 转换表） |

## 3. 密钥实态（运行时验证）

通过 hook 解密器 `[this+0x14]` 的 `SetKey` 参数，实测密钥为：

- 长度 512 字节
- 内容是 **base64 字符串**（如 `aSm5LFUM2x8KV3F8...`，解码后 384 字节）
- base64 原文不在文件中明文出现 → 由 Open 内部从文件读入

## 4. EncType 判定（按扩展名，非文件头）

`GetEncType`（RVA 0x13BB8）**按文件扩展名**匹配内部扩展名列表，不读文件头内容：

| 匹配列表 | 扩展名 | EncType |
|---------|--------|---------|
| list1（字符串 `0x100d98d8`） | `.qmc0 .qmc3 .qmcflac .qmcogg .qmc2 .qmc4 .qmc8 .qmc6 .kgm .krc .kgma .kgmv` | 1 |
| list2（字符串 `0x100d9968`） | `.mflac .mgg .mmp4` | 2 |
| 都不匹配 | 其他 | 0 |

**判定流程**（反汇编）：
```
0x10018005(path)        ; 提取文件扩展名 → CString
0x10005d0b(list1, ext)  ; 在 list1 中 wcsstr 匹配
  匹配 → EncType=1
0x10005d0b(list2, ext)  ; 匹配 list2
  匹配 → EncType=2
否则 → 0
```

**重要推论**：
- EncType 判定与文件内容无关，只认扩展名
- 若扩展名被损坏（如韩文文件名转码丢失），GetEncType 返回 0，Open 直接失败 ——
  这不是格式问题，是文件名编码问题（见 03 文档 §7）
- `_H.mgg`（HQ）和 `_L.mgg`（标准）扩展名都是 `.mgg`，EncType 均为 2，
  解密路径完全相同

## 4.1 mgg 解密验证结果

| 样本 | 质量 | 输入大小 | 输出 | 输出头 |
|------|------|---------|------|--------|
| Ailee - HEAVEN`_H.mgg` | HQ | 8,708,772 | Ogg | `4F 67 67 53` (OggS) |
| Noblesse ...`_L.mgg` | 标准 | 2,845,462 | Ogg | `4F 67 67 53` (OggS) |

mgg 与 mflac 完全同算法，只是输出容器为 Ogg 而非 FLAC。

## 5. 性能特征（补充）

Open/Read 解密本身的耗时分布（原生 C 分段计时，68MB 文件）：

| 阶段 | 耗时 |
|------|------|
| LoadLibrary QQMusicCommon.dll | ~11 ms |
| Open（初始化解密器 + ReadEncKey 读密钥） | ~31 ms |
| Read（解密全文件） | ~520 ms |
| WriteFile | ~43 ms |
| 进程退出时 DLL 清理 | **~5 s**（固有开销） |

**结论**：约 5 秒的固定开销来自 Open 之后进程退出时 `QQMusicCommon.dll` 的
资源清理（只 LoadLibrary 不 Open → 退出 24ms；Open 后退出 → 5s）。
这是 DLL 自身行为，与调用语言无关。批量解密可摊薄此开销。

## 6. 未完成/待深入项

- `[this+0x28]` 累积乘积在 PRGA 中的精确用法（浮点偏移）
- 小文件（keylen ≤ 0x12c）的 0x9930 分支
- `musicex` 尾部 4 字节校验值的算法
- ~~mgg Open 失败~~ → 已确认是文件名编码问题，非格式问题（见 03 文档 §7）
