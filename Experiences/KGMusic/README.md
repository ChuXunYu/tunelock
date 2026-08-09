# 酷狗音乐 KGG 解密逆向经验库

> 目标：沉淀酷狗 KGG 加密音频的逆向方法、算法结论与工具，
> 使将来酷狗更新、加密方案调整后能基于本库快速更新破解方案。

## 版本基线

| 项目 | 值 |
|------|-----|
| 分析日期 | 2026-08-09 |
| 酷狗版本 | 20.1.41.27870 |
| 安装目录 | `E:\KGMusic\20.1.41.27870` |
| 缓存目录 | `D:\KuGou\Temp\`（含 `.kg!` 下载缓存） |
| 关键数据库 | `%APPDATA%\KuGou8\KGMusicV3.db`（AES 分页加密，8.4MB） |
| 样本文件 | `musics\KGMusic\Daniel Powter - Free Loop*.kgg/kgma` |

## 核心结论速览

1. **`.kgg` 文件 = 1024(0x400) 字节明文头部 + 加密音频流**
   - 头 16 字节固定 KGM Magic：`7C D5 32 EB 86 02 7F 4B A8 AF A6 8E 0F FF 99 14`
   - `audio_offset`(0x10)=0x400，`crypto_ver`(0x14)=5
   - `audio_hash`(ASCII hex) 在偏移 **0x48**（`0x3C+8` 处先读 hash_len）
   - `.kgma` = crypto_ver 3（旧版，数据库无 eKey，无法解密）
2. **解密核心 = `QMDECRYPTION.dll`**（腾讯 QQ 音乐模块，被酷狗复用）
   - 导出 C API：`CreateDecryption(key,keylen)` / `Decrypt(ctx,index,data,len)` / `DestroyDecryption(ctx)`
   - **正确用法**：`CreateDecryption` 传入**数据库 eKey 的 base64 原文**（DLL 内部解码+TEA派生），
     `Decrypt(ctx, 0, audio, len)` 就地解密。不要传派生的二进制 key（会乱码）
   - 内含字符串 `QQMusic EncV2,Key:`、base64 表、tan 正弦随机数（salt=0x6A）
3. **真正的密钥不随 kgg 文件分发**，而是存在本地数据库 `KGMusicV3.db`
   - 数据库本身 AES-128-CBC 分页加密（master key + 页号派生 key/IV）
   - 解密后 SQLite，查 `ShareFileItems` 表 `WHERE EncryptionKeyId=audio_hash` → `EncryptionKey`(eKey)
4. **eKey 派生算法**（与 QMDECRYPTION.dll 内部一致）：
   - base64 解码 eKey → 若以 `QQMusic EncV2,Key:` 开头走 v2（双层 TEA+base64），否则走 v1
   - v1：`tan(106+i*0.1)*100` 生成 8 字节盐，与 raw 前 8 字节交错成 16 字节 TEA key，
     对 raw[8:] 做腾讯 TEA(CBC) 解密 → 最终密钥 = raw[:8] + 解密结果（512 字节）
5. **解密算法（kgg）**：密钥长度 >300 → RC4Cipher，否则 MapCipher
   - Map：`key[(off²+71214)%len]` 循环移位 `r=((idx&7)+4)%8`
   - RC4：KSA + 段(5120)/首段(128) 分块 PRGA，段内按 `hash/denom*100` 跳位
6. **kgma / kgm（crypto_ver 3）**：与 kgg 完全不同的旧版算法，**密钥内嵌文件头**（0x1C 处 16 字节）
   - 无需数据库 eKey；流解密用 `table1/table2/MaskV2PreDef` 三张 272 字节表
   - 见 `02-算法逆向记录.md` 对应章节与 `scripts/kgm_dec.c`
7. **输出格式按头部魔术字节识别**：`fLaC`→FLAC、`OggS`→OGG、`ID3`/`0xFFF?`→MP3
   - 质量等级：`high`(大)→FLAC，`320G`→OGG(320k)，`128a`→OGG(128k)
8. **离线可解**：不运行酷狗，只要本机数据库里有该歌曲 eKey 即可（酷狗能播的歌就能解）

## 重要踩坑（务必先读）

| 坑 | 现象 | 真相 |
|----|------|------|
| `QMDECRYPTION.dll` 以为不能直接解 kgg | 用派生 key（二进制/再 base64）喂它 Decrypt 输出乱码 | **应传数据库 eKey 的 base64 原文**（DLL 内部自行解码+TEA 派生），修正后 142/142 kgg 全解 |
| kugou 无法在无界面环境 hook | KuGou.exe/ginkgo.exe 启动即退出(0) | 酷狗是 CEF 宿主，依赖网络/登录/特定会话，命令行无法正常启动，proxy DLL 方案不可行 |
| kgma 以为解不了 | 数据库里 kgma 记录 eKey 为空 | **kgma 密钥内嵌文件头（0x1C 16 字节）**，根本不查数据库；用 KGM 流算法（table1/table2/MaskV2PreDef）即可解，167/167 实测成功 |
| 数据库看似乱码 | 读出来不是 SQLite | 整个数据库被 AES-128-CBC 按 0x400 分页加密，第 1 页特殊（页头校验+置换），需逐页解密 |

## 工具链

| 文件 | 说明 |
|------|------|
| `tools/KgDec.py` | **kgg 解密工具**（纯 Python，需 `pip install cryptography`）。自动定位数据库→解密→查 eKey→RC4/Map 解密→识别格式输出。支持文件/目录批量 |
| `tools/KgDec_dll.py`（见 03 文档） | **推荐路径**：直接 ctypes 调 `QMDECRYPTION.dll`，`CreateDecryption(eKey原文)` 解密，256/512 key 通吃且快 |
| `Experiences/KGMusic/scripts/kgm_dec.c` | **kgma/kgm 解密器**（C，mingw64 编译）。密钥内嵌文件头，三张 272 字节表流解密，批量递归目录 |
| 算法来源 | kgg：移植自 GitHub `Aaron-gx/KGG-Decryptor`（MIT）+ `QMDECRYPTION.dll` 反汇编验证；kgma：移植自开源 `AudioDecrypt`（KGM.cpp） |

## 文档索引

| 文件 | 内容 |
|------|------|
| `01-文件格式分析.md` | kgg/kgma 头部结构、audio_hash 定位、缓存/数据库定位 |
| `02-算法逆向记录.md` | QMDECRYPTION.dll 反汇编、CreateDecryption key 解析、TEA/RC4/Map 算法 |
| `03-工具链构建.md` | 数据库 AES 分页解密、KgDec.py 使用与依赖 |
| `04-版本更新应对指南.md` | 酷狗更新后如何定位新算法/新密钥来源 |

## 关键发现

- 酷狗复用了腾讯 QQ 音乐的 `QMDECRYPTION.dll`（PDB 路径 `QMDecryption.pdb`），
  但密钥管理是酷狗自己的（本地数据库分发表，而非 QQ 的 EncV2 内嵌）。
- 算法本质与 QQ 音乐 mflac 同源（定制 RC4 + tan 浮点随机偏移 + 512 字节密钥），
  可对照 `Experiences\QQMusic\02-算法逆向记录.md`。
