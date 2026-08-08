using System;
using System.IO;
using System.Runtime.InteropServices;

class QqmKeyDump
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

    static int Main(string[] args)
    {
        SetDllDirectory(@"E:\QQMusic");
        IntPtr h = LoadLibrary("QQMusicCommon.dll");

        Ctor ctor = (Ctor)Marshal.GetDelegateForFunctionPointer(GetProcAddress(h, "??0EncAndDesMediaFile@@QAE@XZ"), typeof(Ctor));
        Open open = (Open)Marshal.GetDelegateForFunctionPointer(GetProcAddress(h, "?Open@EncAndDesMediaFile@@QAE_NPB_W_N1@Z"), typeof(Open));

        IntPtr obj = Marshal.AllocHGlobal(0x28);
        for (int i = 0; i < 0x28; i++) Marshal.WriteByte(obj, i, 0);
        ctor(obj);
        IntPtr fn = Marshal.StringToHGlobalUni(Path.GetFullPath(args[0]));
        IntPtr ok = open(obj, fn, 1, 0);
        Console.WriteLine("Open=" + ok.ToInt32());

        // decryptor 对象 [obj+0x14]
        IntPtr dec = new IntPtr(Marshal.ReadInt32(obj, 0x14));
        Console.WriteLine("decryptor=0x" + dec.ToInt32().ToString("X8"));
        if (dec != IntPtr.Zero)
        {
            // decryptor 对象结构: [0]=vtable, [4]=key ptr, [8]=keylen, [0x28]=state ptr, [0x2c]=sbox ptr
            IntPtr keyPtr = new IntPtr(Marshal.ReadInt32(dec, 4));
            int keylen = Marshal.ReadInt32(dec, 8);
            Console.WriteLine("key ptr=0x" + keyPtr.ToInt32().ToString("X8") + " keylen=" + keylen);
            if (keyPtr != IntPtr.Zero && keylen > 0 && keylen < 4096)
            {
                byte[] key = new byte[keylen];
                Marshal.Copy(keyPtr, key, 0, keylen);
                Console.WriteLine("KEY: " + BitConverter.ToString(key));
                Console.WriteLine("KEY ascii: " + System.Text.Encoding.ASCII.GetString(key));
            }
            IntPtr sbox = new IntPtr(Marshal.ReadInt32(dec, 0x2c));
            int statelen = Marshal.ReadInt32(dec, 8);
            Console.WriteLine("sbox ptr=0x" + sbox.ToInt32().ToString("X8"));
            IntPtr v28 = new IntPtr(Marshal.ReadInt32(dec, 0x28));
            Console.WriteLine("[0x28]=" + Marshal.ReadInt32(dec, 0x28));
        }
        return 0;
    }
}
