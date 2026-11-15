#!/usr/bin/env python3
"""
解密器密钥 dump 说明

目标: 提取 EncAndDesMediaFile 解密器持有的实际密钥，用于对比新旧版本算法。

原理（见 02-algorithm.md）:
  Open 成功后:
    [obj + 0x14] = 解密器对象指针
    解密器 [dec + 4] = key 指针, [dec + 8] = keylen
    实测: keylen=512, 内容是 base64 字符串

实现方式（C#，32 位）:
  用 GetProcAddress 拿 ??0EncAndDesMediaFile 等导出，thiscall 调用，
  Open 成功后读 [obj+0x14] 指向的解密器对象字段。

对应代码（写入 QqmKeyDump.cs 编译运行）:
  dec = Marshal.ReadInt32(obj, 0x14)
  keyPtr = Marshal.ReadInt32(dec, 4)
  keylen = Marshal.ReadInt32(dec, 8)
  key = Marshal.Copy(keyPtr, ...)

注意:
  - 需要 32 位 csc (C:\\Windows\\Microsoft.NET\\Framework\\v4.0.30319\\csc.exe /platform:x86)
  - SetDllDirectory(E:\\QQMusic) 必须在 LoadLibrary 之前
  - 完整源码见仓库 tools/QqmKeyDump.cs (按需保留)
"""
print(__doc__)
