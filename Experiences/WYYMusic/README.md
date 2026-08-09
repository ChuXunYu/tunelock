# 网易云音乐 NCM 解密逆向经验库

> 目标：沉淀网易云音乐 ncm 加密音频的逆向方法、算法结论与工具，
> 使将来网易云更新、加密方案调整后能基于本库快速更新破解方案。

## 版本基线

| 项目 | 值 |
|------|-----|
| 分析日期 | 2026-08-10 |
| 网易云版本 | 3.1.37.205354 |
| 安装目录 | `E:\CloudMusic` |
| 缓存目录 | `D:\Temp\WYY_caches`（当前为空） |
| 关键模块 | `cloudmusic.dll`（x64，image_base 0x180000000，含全部 ncm 解密常量） |
| 样本文件 | `musics\WYYMusic\*.ncm`（4 个，覆盖四种音质） |

## 核心结论速览

1. **`.ncm` = 固定文件头 + 加密 meta + 专辑封面 + 加密音频流**
   - magic 8 字节：`CTENFDAM`
   - keydata(128B) 加密 → `sCoreKey` 解密 → `neteasecloudmusic`+歌曲ID → 取 `[17:]` 作 RC4 key
   - meta 加密 → `sModifyKey` 解密 → JSON（歌名/歌手/专辑/码率）
2. **加密算法与音质无关**：高品质无损/无损/极高/标准 **共用同一算法**
   - 只是被加密的音频内容不同：FLAC vs MP3、码率不同
3. **密钥内嵌文件**：解密 key 全部由文件自身的 keydata 派生，**不依赖账号/数据库/网络**
   - 换账号、换电脑、拷给任何人都能离线解（和 QQ 音乐 mflac 同类，但比酷狗更强）
4. **算法实质**：`buildKeyBox(key)` 生成 256 字节 S-box（类 RC4 KSA 变体）+
   预计算 256 字节 XOR 表，音频逐字节 `buf[i] ^= T[i & 0xFF]`
5. **meta 结构**：`"RUPC"` 是假象——那是 `"163 "` XOR 0x63 后的密文形态
   - 整个 meta 先逐字节 XOR 0x63，再去前缀 `163 key(Don't modify):`，
     base64 解码，`sModifyKey` AES-ECB 解密，去前缀 `music:` → JSON
6. **输出格式识别**：前 3 字节 `ID3` → mp3，否则 `fLaC` → flac

## 四种音质实测（2026-08-10）

| 音质 | 样本 | 输出 | 参数 |
|------|------|------|------|
| 高品质无损 | 林俊杰 - 爱不会绝迹 | FLAC | 44100Hz / 2ch / 16-bit |
| 无损 | Charlie Puth - I Don't Think That I Like Her | FLAC | 44100Hz / 2ch / 24-bit |
| 极高 | Muyoi, 徐梦洁 - 一点 | MP3 | 320kbps |
| 标准 | YOASOBI - 群青 | MP3 | 128kbps |

> 注：meta JSON 内 `bitrate` 字段（如 999000/320000/128000）即为音质标识；
> "高品质无损"与"无损"都是 FLAC，实际位深由歌曲母带规格决定（样本中无损反而 24-bit）。

## 重要踩坑（务必先读）

| 坑 | 现象 | 真相 |
|----|------|------|
| 用老版 ncmdump 思路解 keybox 失败 | keydata XOR 0x64 后再差分/异或都得不到固定 keybox | keydata 不是"加密后需解开的固定 keybox"，而是直接用 `sCoreKey` **AES-ECB 解密**的密文 |
| 误判为新格式 | meta 以 `RUPC` 开头，且 keybox 前 16 字节全文件相同 | `RUPC` = `"163 "` XOR 0x63；keybox 前 16 字节相同 = AES-ECB 加密相同明文块 `neteasecloudmusi` |
| `CTENFDAM`/`RUPC` 搜不到 | 全安装目录搜不到这两个字符串 | magic/前缀均为**运行时构造或加密态**，客户端代码里只存固定 key 与 `neteasecloudmusic` 等明文 |
| 与 ncmdump 输出哈希不同 | 同文件哈希不一致 | ncmdump 用 TagLib 额外写了标签（标题/封面），音频流本体完全一致，需剥离标签后对比 |

## 工具链

| 文件 | 说明 |
|------|------|
| `tools/WYYDec.py` | **最终解密工具**（纯 Python，需 `pip install cryptography`）。支持文件/目录批量，解密+识别格式+打印 meta 信息 |
| 算法来源 | 对照开源 `taurusxin/ncmdump`(v1.5.1) 移植，已交叉验证（FLAC STREAMINFO / MP3 帧逐字节一致），并用 cloudmusic.dll 中的明文 key 常量佐证 |

## 文档索引

| 文件 | 内容 |
|------|------|
| `01-文件格式分析.md` | ncm 文件头/keydata/meta/封面/音频流结构、长度字段定位 |
| `02-算法逆向记录.md` | buildKeyBox/XOR 表推导、meta 解密链、cloudmusic.dll 常量定位与 AES 佐证 |
| `03-工具链构建.md` | WYYDec.py 使用、依赖、验证方法 |
| `scripts/WYYDec.py` | 解密工具归档副本 |

## 关键发现

- 网易云 ncm 是"文件自带密钥"型（同 QQ 音乐 mflac），比酷狗（密钥锁本机数据库）更易离线转移。
- 四档音质算法无差别，差异仅在被加密的 FLAC/MP3 规格上；meta JSON 是音质档位的权威来源。
