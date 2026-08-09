/*
 * QqmDec.c - QQ音乐 mflac/mgg 离线解密工具 (原生C, 32位)
 *
 * 直接调用 QQMusicCommon.dll 的 EncAndDesMediaFile 类完成解密。
 * 类方法使用 MSVC thiscall 约定，MinGW gcc 的 __thiscall 属性直接支持。
 *
 * 编译(32位, msys2 mingw32):
 *   gcc -O2 -static -o QqmDec.exe QqmDec.c -lkernel32 -luser32
 *
 * 用法:
 *   QqmDec.exe <src.mflac> <out.flac>
 *   QqmDec.exe <srcDir> <outDir>
 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define QQ_DIR_DEFAULT "E:\\QQMusic"
#define OBJ_SIZE 0x28

/* EncAndDesMediaFile 类方法 (thiscall: this 进 ECX) */
typedef void  (__thiscall *FnCtor)(void *self);
typedef int   (__thiscall *FnOpen)(void *self, const wchar_t *path, char b1, char b2);
typedef unsigned int (__thiscall *FnGetSize)(void *self);
typedef unsigned int (__thiscall *FnRead)(void *self, unsigned char *buf, unsigned int size, long long offset);
typedef void  (__thiscall *FnDtor)(void *self);

static HMODULE g_hDll = NULL;
static FnCtor g_ctor;
static FnOpen g_open;
static FnGetSize g_getSize;
static FnRead g_read;
static FnDtor g_dtor;

static void fatal(const char *msg)
{
    fprintf(stderr, "[FATAL] %s (err=%lu)\n", msg, GetLastError());
    exit(1);
}

static int init_dll(const char *qqDir)
{
    typedef BOOL (WINAPI *FnSetDllDir)(LPCSTR);
    HMODULE hK = LoadLibraryA("kernel32.dll");
    FnSetDllDir setDllDir = (FnSetDllDir)GetProcAddress(hK, "SetDllDirectoryA");
    if (setDllDir) setDllDir(qqDir);

    g_hDll = LoadLibraryA("QQMusicCommon.dll");
    if (!g_hDll) fatal("LoadLibrary QQMusicCommon.dll");

    g_ctor   = (FnCtor)GetProcAddress(g_hDll, "??0EncAndDesMediaFile@@QAE@XZ");
    g_open   = (FnOpen)GetProcAddress(g_hDll, "?Open@EncAndDesMediaFile@@QAE_NPB_W_N1@Z");
    g_getSize= (FnGetSize)GetProcAddress(g_hDll, "?GetSize@EncAndDesMediaFile@@QAEKXZ");
    g_read   = (FnRead)GetProcAddress(g_hDll, "?Read@EncAndDesMediaFile@@QAEKPAEK_J@Z");
    g_dtor   = (FnDtor)GetProcAddress(g_hDll, "??1EncAndDesMediaFile@@QAE@XZ");
    if (!g_ctor || !g_open || !g_getSize || !g_read || !g_dtor)
        fatal("GetProcAddress for EncAndDesMediaFile methods");
    return 0;
}

/* 返回 0 成功 */
static int decrypt_file(const wchar_t *src, const wchar_t *dst)
{
    unsigned char *obj, *buf;
    unsigned int size, got;
    HANDLE hOut;
    DWORD written;
    int ok = 1;

    obj = (unsigned char*)calloc(1, OBJ_SIZE);
    if (!obj) { fprintf(stderr, "calloc obj failed\n"); return 1; }

    g_ctor(obj);
    if (!g_open(obj, src, 1, 0)) {
        fprintf(stderr, "Open failed (err=%lu)\n", GetLastError());
        goto done;
    }

    size = g_getSize(obj);
    buf = (unsigned char*)malloc(size);
    if (!buf) { fprintf(stderr, "malloc buf failed\n"); goto done; }

    got = g_read(obj, buf, size, 0);
    if (got == 0) { fprintf(stderr, "Read returned 0\n"); free(buf); goto done; }

    hOut = CreateFileW(dst, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (hOut == INVALID_HANDLE_VALUE) { fprintf(stderr, "CreateFileW failed (err=%lu)\n", GetLastError()); free(buf); goto done; }
    WriteFile(hOut, buf, got, &written, NULL);
    CloseHandle(hOut);
    free(buf);
    ok = 0;

done:
    g_dtor(obj);
    free(obj);
    return ok;
}

int main(int argc, char **argv)
{
    const char *qqDir;
    char qqDirBuf[MAX_PATH];

    if (argc < 3) {
        printf("usage: QqmDec.exe <src.mflac> <out.flac>\n");
        printf("       QqmDec.exe <srcDir> <outDir>\n");
        return 1;
    }

    /* QQ 目录：exe 同目录优先，否则默认 */
    GetModuleFileNameA(NULL, qqDirBuf, MAX_PATH);
    {
        char *slash = strrchr(qqDirBuf, '\\');
        if (slash) *slash = 0;
    }
    {
        char probe[MAX_PATH];
        sprintf(probe, "%s\\QQMusicCommon.dll", qqDirBuf);
        qqDir = (GetFileAttributesA(probe) != INVALID_FILE_ATTRIBUTES) ? qqDirBuf : QQ_DIR_DEFAULT;
    }

    init_dll(qqDir);

    {
        DWORD attr = GetFileAttributesA(argv[1]);
        int isDir = (attr != INVALID_FILE_ATTRIBUTES && (attr & FILE_ATTRIBUTE_DIRECTORY));
        if (isDir) {
            WIN32_FIND_DATAA fd;
            HANDLE hFind;
            char pat[MAX_PATH];
            int n = 0;
            sprintf(pat, "%s\\*", argv[1]);
            CreateDirectoryA(argv[2], NULL);
            hFind = FindFirstFileA(pat, &fd);
            if (hFind != INVALID_HANDLE_VALUE) {
                do {
                    const char *ext;
                    const char *dot;
                    char base[MAX_PATH], full[MAX_PATH], out[MAX_PATH];
                    size_t len;
                    wchar_t wsrc[MAX_PATH], wdst[MAX_PATH];

                    if (fd.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) continue;
                    ext = strrchr(fd.cFileName, '.');
                    if (!ext) continue;
                    if (strcmp(ext, ".mflac") != 0 && strcmp(ext, ".mgg") != 0) continue;

                    dot = strrchr(fd.cFileName, '.');
                    len = (size_t)(dot - fd.cFileName);
                    memcpy(base, fd.cFileName, len);
                    base[len] = 0;
                    sprintf(out, "%s\\%s.%s", argv[2], base,
                            strcmp(ext, ".mflac") == 0 ? "flac" : "ogg");
                    sprintf(full, "%s\\%s", argv[1], fd.cFileName);

                    MultiByteToWideChar(CP_ACP, 0, full, -1, wsrc, MAX_PATH);
                    MultiByteToWideChar(CP_ACP, 0, out, -1, wdst, MAX_PATH);
                    if (decrypt_file(wsrc, wdst) == 0) {
                        printf("[OK] %s\n", fd.cFileName);
                        n++;
                    } else {
                        printf("[FAIL] %s\n", fd.cFileName);
                    }
                } while (FindNextFileA(hFind, &fd));
                FindClose(hFind);
            }
            printf("done: %d decrypted\n", n);
        } else {
            wchar_t wsrc[MAX_PATH], wdst[MAX_PATH];
            MultiByteToWideChar(CP_ACP, 0, argv[1], -1, wsrc, MAX_PATH);
            MultiByteToWideChar(CP_ACP, 0, argv[2], -1, wdst, MAX_PATH);
            return decrypt_file(wsrc, wdst);
        }
    }

    return 0;
}
