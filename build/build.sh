#!/usr/bin/env bash
# TuneLock 原生工具编译脚本（Linux / WSL / msys2 / Git Bash）
#
#   bash build/build.sh          # 两个都编（能编哪个编哪个）
#   bash build/build.sh kgm      # 只编 kgm_dec.exe
#   bash build/build.sh qq       # 只编 QqmDec.exe（需要 32 位 mingw：i686-w64-mingw32-gcc）
set -u
cd "$(dirname "$0")/.." || exit 1
target="${1:-all}"

build_kgm() {
    local gcc="${GCC64:-$(command -v x86_64-w64-mingw32-gcc || command -v gcc)}"
    if [ -z "${gcc:-}" ]; then echo "[跳过] 没找到 64 位 gcc"; return 1; fi
    mkdir -p tools/native/kugou/bin
    echo "==> kgm_dec.exe  <-  $gcc"
    "$gcc" -O2 -o tools/native/kugou/bin/kgm_dec.exe tools/native/kugou/kgm_dec.c || return 1
    echo "    产物: tools/native/kugou/bin/kgm_dec.exe"
}

build_qq() {
    local gcc="${GCC32:-$(command -v i686-w64-mingw32-gcc)}"
    if [ -z "${gcc:-}" ]; then
        echo "[跳过] 没找到 32 位 mingw（QQMusicCommon.dll 是 32 位，必须 i686-w64-mingw32-gcc）"
        return 1
    fi
    mkdir -p tools/native/qqmusic/bin
    echo "==> QqmDec.exe  <-  $gcc"
    "$gcc" -O2 -municode -o tools/native/qqmusic/bin/QqmDec.exe \
        tools/native/qqmusic/QqmDec.c -lkernel32 -luser32 || return 1
    echo "    产物: tools/native/qqmusic/bin/QqmDec.exe"
}

rc=0
case "$target" in
    all) build_kgm || rc=1; build_qq || rc=1 ;;
    kgm) build_kgm || rc=1 ;;
    qq)  build_qq  || rc=1 ;;
    *)   echo "用法: bash build/build.sh [all|kgm|qq]"; exit 2 ;;
esac
echo
echo "提示：QQ 解密需要把 QQMusicCommon.dll 与 CommonFunction.dll 放进 tools/native/qqmusic/bin/"
exit $rc
