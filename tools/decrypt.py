#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""三平台解密核心：GUI 与命令行共用的一套调度逻辑。

分工：
  - QQ 音乐 (mflac/mgg)：subprocess 调 ``tools/native/qqmusic/QqmDec.exe``
    （那是唯一能解腾讯 EncV2 的方式，DLL 里是私有实现）
  - 酷狗   (kgg)：复用 ``kugou.py``（纯 Python：解数据库 → 查 eKey → RC4/Map）
  - 网易云 (ncm)：复用 ``netease.py``（密钥内嵌文件）

本模块只做文件级调度与降级判断，不碰界面，方便脚本/批处理/服务端复用。
"""
import os
import subprocess
import sys
import threading

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)

QQM_DIR = os.path.join(TOOLS_DIR, "native", "qqmusic")
QQM_BIN = os.path.join(QQM_DIR, "bin")
QQM_EXE_CANDIDATES = [
    os.path.join(QQM_BIN, "QqmDec.exe"),
    os.path.join(QQM_DIR, "QqmDec.exe"),
    os.environ.get("QQM_EXE", ""),
]
QQM_EXE = next((p for p in QQM_EXE_CANDIDATES if p and os.path.exists(p)),
               QQM_EXE_CANDIDATES[0])
QQM_DLL = os.path.join(QQM_DIR, "QQMusicCommon.dll")
QQM_LOCAL_DLL = os.path.join(QQM_BIN, "QQMusicCommon.dll")
QQM_HELPER_DLL = os.path.join(QQM_BIN, "CommonFunction.dll")
QQM_TIMEOUT = 600

# QQ 音乐安装目录：环境变量 QQMUSIC_DIR 优先，其次常见安装路径
QQ_DIRS = [d for d in (
    os.environ.get("QQMUSIC_DIR"),
    r"E:\QQMusic",
    r"D:\QQMusic",
    r"C:\Program Files\QQMusic",
    r"C:\Program Files (x86)\QQMusic",
) if d]

TARGET_EXTS = (".mflac", ".mgg", ".kgg", ".ncm")
QQ_EXTS = (".mflac", ".mgg")
PY_EXTS = (".kgg", ".ncm")

try:
    import cryptography  # noqa: F401  必须先成功，否则 netease/kugou 的 sys.exit 会退出进程
    import kugou
    import netease
    DEC_OK = True
    IMPORT_ERR = ""
except Exception as _exc:  # pragma: no cover - 缺依赖时的降级提示
    DEC_OK = False
    IMPORT_ERR = str(_exc)


class DecryptError(RuntimeError):
    """解密失败（格式不认识 / 缺 eKey / 输出无法识别）。"""


# ---------------------------------------------------------------- 工具函数
def platform_of(path):
    """按扩展名判断平台：'qq' / 'kugou' / 'netease'，不支持返回 None。"""
    ext = os.path.splitext(path)[1].lower()
    if ext in QQ_EXTS:
        return "qq"
    if ext == ".kgg":
        return "kugou"
    if ext == ".ncm":
        return "netease"
    return None


def is_supported(path):
    return platform_of(path) is not None


# ---------------------------------------------------------------- 酷狗 / 网易云
_ekey_lock = threading.Lock()
_ekey_map = None


def _get_ekey_map():
    """懒加载酷狗 eKey 数据库（整库只解一次，批量时不重复解密）。"""
    global _ekey_map
    with _ekey_lock:
        if _ekey_map is None:
            db = kugou.find_db()
            if not db:
                raise DecryptError("未找到 KGMusicV3.db（需本机酷狗有该歌 eKey）")
            _ekey_map = kugou.load_ekey_map(db)
            if _ekey_map is None:
                raise DecryptError("KGMusicV3.db 解密失败")
        return _ekey_map


def kgg_decrypt(src):
    """解一个 kgg：返回 (音频字节, 扩展名, None)。"""
    with open(src, "rb") as f:
        data = f.read()
    r = kugou.parse_header(data)
    if r is None:
        raise DecryptError("不是 KGG 文件")
    if r[0] is None:
        raise DecryptError("不支持的 crypto version")
    (audio_offset, audio_hash), _ = r
    ekey = _get_ekey_map().get(audio_hash)
    if not ekey:
        raise DecryptError("本机数据库无该歌 eKey (hash=%s)" % audio_hash)
    raw = kugou.derive_key(ekey)
    if raw is None:
        raise DecryptError("eKey 派生失败")
    cipher = kugou.Rc4Cipher(raw) if len(raw) > 300 else kugou.MapCipher(raw)
    audio = bytearray(data[audio_offset:])
    cipher.decrypt(audio, 0)
    ext = kugou.sniff_ext(bytes(audio))
    if ext == "bin":
        raise DecryptError("无法识别音频格式")
    return bytes(audio), ext, None


def ncm_decrypt(src):
    """解一个 ncm：返回 (音频字节, 扩展名, meta 摘要)。"""
    with open(src, "rb") as f:
        data = f.read()
    audio, meta, _ = netease.decrypt_ncm(data)
    ext = netease.sniff_ext(audio)
    if ext == "bin":
        raise DecryptError("无法识别音频格式")
    return audio, ext, netease.format_meta(meta)


def py_decrypt(src):
    """按扩展名分发到 kgg / ncm 的纯 Python 解密。"""
    plat = platform_of(src)
    if plat == "kugou":
        return kgg_decrypt(src)
    if plat == "netease":
        return ncm_decrypt(src)
    raise DecryptError("未知格式 %s（纯 Python 路径只支持 kgg/ncm）"
                       % (os.path.splitext(src)[1] or src))


# ---------------------------------------------------------------- QQ 音乐
def qq_dll_path():
    """找到可用的 QQMusicCommon.dll：exe 同目录优先，其次 QQ 音乐安装目录。"""
    for cand in (QQM_LOCAL_DLL, QQM_DLL):
        if os.path.exists(cand):
            return cand
    for d in QQ_DIRS:
        cand = os.path.join(d, "QQMusicCommon.dll")
        if os.path.exists(cand):
            return cand
    return None


def qq_requirements():
    """QQ 音乐解密链的三块拼图各就位没：exe / 中转 DLL / 私有解密 DLL。

    ``CommonFunction.dll`` 必须和 exe 同目录（QQMusicCommon.dll 内部按 exe 所在目录找它），
    所以这里单独检查它，缺了就给出明确提示而不是丢一个 Open failed。
    """
    return {
        "exe": os.path.exists(QQM_EXE),
        "helper_dll": os.path.exists(QQM_HELPER_DLL),
        "qq_dll": qq_dll_path() is not None,
    }


def qq_ready():
    """QQ 路径是否可用：exe 在、中转 DLL 在、私有解密 DLL 找得到。"""
    req = qq_requirements()
    return all(req.values())


def qq_hint():
    """拼一句人话，说清 QQ 路径还缺什么。"""
    req = qq_requirements()
    missing = []
    if not req["exe"]:
        missing.append("QqmDec.exe（跑 build/build.ps1 编译，产物放 %s）" % QQM_BIN)
    if not req["helper_dll"]:
        missing.append("CommonFunction.dll（从 QQ 音乐安装目录复制到 %s）" % QQM_BIN)
    if not req["qq_dll"]:
        missing.append("QQMusicCommon.dll（装 QQ 音乐，或设 QQMUSIC_DIR 指向安装目录）")
    return "；".join(missing)


def qq_decrypt(src, out):
    """调 QqmDec.exe 解一个 mflac/mgg，写出到 out；返回 (ok, msg)。"""
    if not qq_ready():
        return False, "QQ 解密链未就绪：" + qq_hint()
    proc = subprocess.Popen([QQM_EXE, src, out],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        ob, eb = proc.communicate(timeout=QQM_TIMEOUT)
    except subprocess.TimeoutExpired:
        proc.kill()
        return False, "解密超时(>%ds)" % QQM_TIMEOUT
    text = ob.decode("utf-8", "replace") + eb.decode("utf-8", "replace")
    if proc.returncode == 0 and "FAIL" not in text:
        return True, ""
    tail = text.strip().splitlines()[-1] if text.strip() else "QqmDec 失败(code=%d)" % proc.returncode
    return False, tail


def qq_output_ext(src):
    return ".flac" if os.path.splitext(src)[1].lower() == ".mflac" else ".ogg"


# ---------------------------------------------------------------- 任务收集
def parse_inputs(text):
    """把输入框文本（换行/分号分隔、可带引号）拆成路径列表。"""
    out = []
    for line in text.replace(";", "\n").splitlines():
        line = line.strip().strip('"').strip()
        if line:
            out.append(line)
    return out


def collect_tasks(paths, recursive=True):
    """展开输入为 [(src_abs, rel, default_root)]。

    default_root：文件夹输入时的默认输出根（父目录/文件夹名_decoded）。
    """
    tasks = []
    for p in paths:
        p = p.strip().strip('"')
        if not p:
            continue
        if os.path.isdir(p):
            root_in = os.path.abspath(p)
            default_root = os.path.join(os.path.dirname(root_in),
                                        os.path.basename(root_in) + "_decoded")
            for dp, dns, fns in os.walk(root_in):
                dns[:] = [d for d in dns if not d.endswith("_decoded")]
                for fn in fns:
                    if is_supported(fn):
                        src = os.path.join(dp, fn)
                        tasks.append((src, os.path.relpath(src, root_in), default_root))
                if not recursive:
                    dns[:] = []
        elif os.path.isfile(p) and is_supported(p):
            tasks.append((os.path.abspath(p), os.path.basename(p), None))
    return tasks


def resolve_output(src, rel, droot, out_root, out_file, single):
    """决定输出目录与输出基名（不含扩展名）。"""
    if out_file and single:
        return os.path.dirname(out_file) or ".", os.path.splitext(os.path.basename(out_file))[0]
    if out_root:
        d = out_root
    elif droot:
        d = droot
    else:
        d = os.path.dirname(src)
    sub = os.path.dirname(rel)
    if sub:
        d = os.path.join(d, sub)
    return d, os.path.splitext(os.path.basename(src))[0]
