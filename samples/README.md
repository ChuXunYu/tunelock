# 样本目录（不入库）

本仓库不含任何音频。这里放你自己的正版下载文件用于自测，`.gitignore` 已忽略本目录下的一切
（只保留本说明），所以样本不会误提交。

建议这样摆：

```
samples/
  qqmusic/     *.mflac  *.mgg          # QQ 音乐下载的加密文件
  kugou/       *.kgg    *.kgma  *.kgm  # 酷狗下载的加密文件
  netease/     *.ncm                   # 网易云下载的加密文件
  lyrics/      *.krc    *.lrc          # 歌词（酷狗 krc / 网易云 lrc）
```

先体检，再解密：

```powershell
python -m tools info    samples -r     # 看每个文件属于哪个平台、能不能解
python -m tools decrypt samples -r -o .\decoded
```

各平台的解密前置条件：

| 平台 | 需要什么 |
| --- | --- |
| QQ 音乐 mflac/mgg | `tools/native/qqmusic/bin/QqmDec.exe` + `CommonFunction.dll` + 本机 QQ 音乐安装（提供 `QQMusicCommon.dll`） |
| 酷狗 kgg | 本机 `%APPDATA%\KuGou8\KGMusicV3.db` 里有该歌的 eKey（酷狗能播的歌才有） |
| 酷狗 kgma/kgm | 只要编译好的 `kgm_dec.exe`，密钥内嵌文件头 |
| 网易云 ncm | 只需要 `pip install -r requirements.txt`（密钥内嵌文件） |
