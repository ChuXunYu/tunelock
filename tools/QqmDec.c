/*
 * QqmDec.c - QQ音乐 mflac/mgg 离线解密工具 (原生C, 32位)
 *
 * 直接调用 QQMusicCommon.dll 的 EncAndDesMediaFile 类完成解密。
 * thiscall 约定由 qqm_thunk.s 汇编 thunk 处理（this 进 ECX）。
 *
 * 编译(32位): tcc -m32 -o QqmDec.exe QqmDec.c qqm_thunk.s -lkernel32 -luser32
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

#ifndef CP_ACP
#define CP_ACP 0
#endif
extern int __stdcall MultiByteToWideChar(unsigned int, unsigned long, const char*, int, wchar_t*, int);

#define QQ_DIR_DEFAULT "E:\\QQMusic"
#define OBJ_SIZE 0x28

/* 汇编 thunk 入口（__stdcall，内部把 this 移入 ECX） */
extern void __stdcall ctor_t(void *self);
extern int __stdcall open_t(void *self, const wchar_t *path, char b1, char b2);
extern unsigned int __stdcall getSize_t(void *self);
extern unsigned int __stdcall read_t(void *self, unsigned char *buf, unsigned int size, __int64 offset);
extern void __stdcall dtor_t(void *self);

/* thunk 间接跳转目标（运行时用 GetProcAddress 填充） */
void *ctor_tgt, *open_tgt, *getSize_tgt, *read_tgt, *dtor_tgt;

static HMODULE g_hDll = NULL;

static void fatal(const char *msg)
{
    fprintf(stderr, "[FATAL] %s (err=%lu)\n", msg, GetLastError());
    exit(1);
}

static int init_dll(const char *qqDir)
{
    typedef int (__stdcall *FnSetDllDir)(const char*);
    HMODULE hK = LoadLibraryA("kernel32.dll");
    FnSetDllDir setDllDir = (FnSetDllDir)GetProcAddress(hK, "SetDllDirectoryA");
    if (setDllDir) setDllDir(qqDir);

    g_hDll = LoadLibraryA("QQMusicCommon.dll");
    if (!g_hDll) fatal("LoadLibrary QQMusicCommon.dll");

    ctor_tgt    = (void*)GetProcAddress(g_hDll, "??0EncAndDesMediaFile@@QAE@XZ");
    open_tgt    = (void*)GetProcAddress(g_hDll, "?Open@EncAndDesMediaFile@@QAE_NPB_W_N1@Z");
    getSize_tgt = (void*)GetProcAddress(g_hDll, "?GetSize@EncAndDesMediaFile@@QAEKXZ");
    read_tgt    = (void*)GetProcAddress(g_hDll, "?Read@EncAndDesMediaFile@@QAEKPAEK_J@Z");
    dtor_tgt    = (void*)GetProcAddress(g_hDll, "??1EncAndDesMediaFile@@QAE@XZ");
    if (!ctor_tgt || !open_tgt || !getSize_tgt || !read_tgt || !dtor_tgt)
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

    ctor_t(obj);
    if (!open_t(obj, src, 1, 0)) {
        fprintf(stderr, "Open failed (err=%lu)\n", GetLastError());
        goto done;
    }

    size = getSize_t(obj);
    buf = (unsigned char*)malloc(size);
    if (!buf) { fprintf(stderr, "malloc buf failed\n"); goto done; }

    got = read_t(obj, buf, size, 0);
    if (got == 0) { fprintf(stderr, "Read returned 0\n"); free(buf); goto done; }

    hOut = CreateFileW(dst, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (hOut == INVALID_HANDLE_VALUE) { fprintf(stderr, "CreateFileW failed (err=%lu)\n", GetLastError()); free(buf); goto done; }
    WriteFile(hOut, buf, got, &written, NULL);
    CloseHandle(hOut);
    free(buf);
    ok = 0;

done:
    dtor_t(obj);
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
        wsprintfA(probe, "%s\\QQMusicCommon.dll", qqDirBuf);
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
            wsprintfA(pat, "%s\\*", argv[1]);
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
                    wsprintfA(out, "%s\\%s.%s", argv[2], base,
                              strcmp(ext, ".mflac") == 0 ? "flac" : "ogg");
                    wsprintfA(full, "%s\\%s", argv[1], fd.cFileName);

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
