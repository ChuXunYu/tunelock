using System;
using System.IO;
using System.Runtime.InteropServices;

class QqmDec
{
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    static extern IntPtr LoadLibrary(string lpFileName);
    [DllImport("kernel32.dll", SetLastError = true)]
    static extern bool SetDllDirectory(string lpPathName);
    [DllImport("kernel32.dll", CharSet = CharSet.Ansi, SetLastError = true)]
    static extern IntPtr GetProcAddress(IntPtr hModule, string lpProcName);

    [UnmanagedFunctionPointer(CallingConvention.ThisCall)]
    delegate IntPtr Ctor(IntPtr self);
    [UnmanagedFunctionPointer(CallingConvention.ThisCall)]
    delegate IntPtr Open(IntPtr self, IntPtr filename, byte b1, byte b2);
    [UnmanagedFunctionPointer(CallingConvention.ThisCall)]
    delegate uint GetSize(IntPtr self);
    [UnmanagedFunctionPointer(CallingConvention.ThisCall)]
    delegate uint Read(IntPtr self, IntPtr buf, uint size, long offset);
    [UnmanagedFunctionPointer(CallingConvention.ThisCall)]
    delegate void Dtor(IntPtr self);

    const string QQ_DIR = @"E:\QQMusic";
    static string qqDir = QQ_DIR;
    static readonly string[] DEP_DLLS = {
        "CommonFunction.dll", "MSVCP140.dll", "VCRUNTIME140.dll",
        "vcruntime140.dll", "ucrtbase.dll", "concrt140.dll"
    };

    static void EnsureDeps()
    {
        string exeDir = Path.GetDirectoryName(System.Reflection.Assembly.GetExecutingAssembly().Location);
        foreach (var dll in DEP_DLLS)
        {
            string src = Path.Combine(qqDir, dll);
            string dst = Path.Combine(exeDir, dll);
            if (File.Exists(src) && !File.Exists(dst))
            {
                try { File.Copy(src, dst); } catch { }
            }
        }
    }

    static bool FindQQDir()
    {
        // 1) exe 同目录（若含 QQMusicCommon.dll）
        string exeDir = Path.GetDirectoryName(System.Reflection.Assembly.GetExecutingAssembly().Location);
        if (File.Exists(Path.Combine(exeDir, "QQMusicCommon.dll")))
        {
            qqDir = exeDir;
            return true;
        }
        // 2) 默认目录
        if (Directory.Exists(QQ_DIR) && File.Exists(Path.Combine(QQ_DIR, "QQMusicCommon.dll")))
        {
            qqDir = QQ_DIR;
            return true;
        }
        return false;
    }

    static int Main(string[] args)
    {
        if (args.Length < 2)
        {
            Console.WriteLine("usage: QqmDec.exe <src.mflac> <out.flac>   OR   QqmDec.exe <srcDir> <outDir>");
            return 1;
        }
        string src = args[0];
        string dst = args[1];

        if (!FindQQDir())
        {
            Console.WriteLine("QQMusic dir not found (QQMusicCommon.dll). Expected at: " + QQ_DIR);
            return 2;
        }

        EnsureDeps();
        SetDllDirectory(qqDir);

        IntPtr h = LoadLibrary("QQMusicCommon.dll");
        if (h == IntPtr.Zero)
        {
            Console.WriteLine("LoadLibrary QQMusicCommon.dll failed: " + Marshal.GetLastWin32Error());
            return 3;
        }

        Ctor ctor = (Ctor)Marshal.GetDelegateForFunctionPointer(GetProcAddress(h, "??0EncAndDesMediaFile@@QAE@XZ"), typeof(Ctor));
        Open open = (Open)Marshal.GetDelegateForFunctionPointer(GetProcAddress(h, "?Open@EncAndDesMediaFile@@QAE_NPB_W_N1@Z"), typeof(Open));
        GetSize getSize = (GetSize)Marshal.GetDelegateForFunctionPointer(GetProcAddress(h, "?GetSize@EncAndDesMediaFile@@QAEKXZ"), typeof(GetSize));
        Read read = (Read)Marshal.GetDelegateForFunctionPointer(GetProcAddress(h, "?Read@EncAndDesMediaFile@@QAEKPAEK_J@Z"), typeof(Read));
        Dtor dtor = (Dtor)Marshal.GetDelegateForFunctionPointer(GetProcAddress(h, "??1EncAndDesMediaFile@@QAE@XZ"), typeof(Dtor));

        if (Directory.Exists(src))
        {
            Directory.CreateDirectory(dst);
            int n = 0;
            foreach (var f in Directory.EnumerateFiles(src, "*.*"))
            {
                string ext = Path.GetExtension(f).ToLowerInvariant();
                if (ext != ".mflac" && ext != ".mgg") continue;
                string outName = Path.GetFileNameWithoutExtension(f) + (ext == ".mflac" ? ".flac" : ".ogg");
                string outPath = Path.Combine(dst, outName);
                int rc = DecryptOne(f, outPath, ctor, open, getSize, read, dtor);
                Console.WriteLine((rc == 0 ? "[OK] " : "[FAIL] ") + Path.GetFileName(f));
                if (rc == 0) n++;
            }
            Console.WriteLine("done: " + n + " decrypted");
        }
        else
        {
            Directory.CreateDirectory(Path.GetDirectoryName(dst) ?? ".");
            return DecryptOne(src, dst, ctor, open, getSize, read, dtor);
        }
        return 0;
    }

    static int DecryptOne(string src, string dst, Ctor ctor, Open open, GetSize getSize, Read read, Dtor dtor)
    {
        IntPtr obj = Marshal.AllocHGlobal(0x28);
        try
        {
            for (int i = 0; i < 0x28; i++) Marshal.WriteByte(obj, i, 0);
            ctor(obj);
            IntPtr fn = Marshal.StringToHGlobalUni(Path.GetFullPath(src));
            IntPtr ok = open(obj, fn, 1, 0);
            Marshal.FreeHGlobal(fn);
            if (ok == IntPtr.Zero) return 1;

            uint size = getSize(obj);
            IntPtr buf = Marshal.AllocHGlobal((int)size);
            uint got = read(obj, buf, size, 0);
            byte[] data = new byte[got];
            Marshal.Copy(buf, data, 0, (int)got);
            Marshal.FreeHGlobal(buf);
            File.WriteAllBytes(dst, data);
            return 0;
        }
        finally
        {
            dtor(obj);
            Marshal.FreeHGlobal(obj);
        }
    }
}
