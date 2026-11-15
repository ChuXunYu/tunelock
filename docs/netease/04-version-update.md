# 04 - 版本更新应对指南

> 网易云升级后，若 ncm 无法用 netease.py 解密，按此流程快速定位变更点。

## 1. 指纹速查

先检查旧样本，判断文件结构是否仍一致：

| 指纹 | 旧版(3.1.37) 值 | 检查方式 |
|------|----------------|---------|
| 文件头 magic | `CTENFDAM` | 前 8 字节 |
| keydata 长度 | 0x80 | 偏移 0x0A 4 字节 |
| keydata 前缀解密 | `neteasecloudmusic` | sCoreKey 解密后前 16 字节 |
| meta 前缀(XOR 0x63 后) | `163 key(Don't modify):` | meta 首 22 字节 |
| meta 解密前缀 | `music:` | sModifyKey 解密后前 6 字节 |
| 封面格式 | `FF D8`(JPEG) / `89 50 4E`(PNG) | meta 后图片数据 |
| 音频格式 | `ID3` / `fLaC` | 解密后首字节 |

任一指纹不符 → 进入第 2 步。

## 2. 变更定位流程

1. **新样本对比**：取新旧两个 ncm，逐字段对比（可复用 01 文档结构），
   定位变化的字段（新增长度字段？keydata 变大？meta 前缀变？）
2. **DLL 常量复查**：在 `E:\CloudMusic\cloudmusic.dll` 搜索
   `sCoreKey` / `sModifyKey` / `neteasecloudmusic` / `163 key(Don't modify):`：
   - 若 sCoreKey 变了：keydata 解密密钥更新 → 在 DLL 中找新常量
   - 若 `neteasecloudmusic` 变了：keydata 明文结构变化 → 跳过的字节数/位置可能变
3. **新固定 key 提取**：在 DLL .rdata 搜索 16 字节的 ASCII 可读串，
   结合"被 AES 引用"特征（附近的 AES S-box 常量 0x18DC5A0 可作锚点）定位
4. **meta 解密链**：若 meta 前缀(去 XOR 0x63 后)不再是 `163 key(Don't modify):`，
   检查是否换了 XOR 常量或改为纯 protobuf/JSON 明文，直接在文件里读
5. **算法验证**：用新参数跑通一个样本后，务必用 `ncmdump` 最新版交叉验证
   （`taurusxin/ncmdump` releases），两者一致才可信

## 3. 兜底方案

- 若加密体系整体更换：ncm 文件自带密钥的本质不会变（客户端要离线/断网播放），
  定位思路 = 找"客户端播放 ncm 时读取/解密音频"的函数（搜索文件扩展名、magic、
  AES 调用链），hook 或反汇编取得新算法。
- 跨平台参考：GitHub `unlock-music` 项目维护多种音乐平台格式解密，可对照。
