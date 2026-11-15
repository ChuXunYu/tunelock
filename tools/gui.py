#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TuneLock GUI —— QQ音乐 / 酷狗 / 网易云 加密音频统一解密

三平台解密核心：
  - QQ 音乐 (mflac/mgg):  subprocess 调 tools/native/qqmusic/QqmDec.exe
                          （需 QQMusicCommon.dll：exe 同目录或 QQ 音乐安装目录）
  - 酷狗   (kgg):         复用 tools/kugou.py（需本机 KGMusicV3.db 含该歌 eKey）
  - 网易云 (ncm):         复用 tools/netease.py（密钥内嵌文件）

用法:  python tools/gui.py [路径...]
依赖:  pip install -r requirements.txt
可选:  tkinterdnd2  # 启用文件/文件夹拖拽

输出规则:
  - 输入为文件  -> 默认输出到同目录, 同名换扩展名
  - 输入为文件夹 -> 默认输出到父目录下 "文件夹名_decoded", 保持子目录结构
  - 输出框留空=按上述默认; 填输出文件夹=输出到该文件夹;
    "选择输出文件"=把解密结果写到指定文件(仅单个输入文件时生效)
"""
import os, sys, json, queue, threading, winsound
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    HAVE_DND = True
except Exception:
    HAVE_DND = False

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)

# 解密核心、任务收集都在 decrypt.py（CLI 复用同一份，避免两套逻辑漂移）
import decrypt
from decrypt import (
    DEC_OK,
    QQ_EXTS,
    TARGET_EXTS,
    collect_tasks,
    parse_inputs,
    py_decrypt,
    qq_decrypt,
)

IMPORT_ERR = decrypt.IMPORT_ERR
CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".tunelock_gui.json")


# ---------------------------------------------------------------- GUI
class MusicDecApp:
    def __init__(self, root):
        self.root = root
        self.msgq = queue.Queue()
        self.cancel_event = threading.Event()
        self.worker = None
        self.current_proc = None

        root.title("TuneLock · QQ音乐 / 酷狗 / 网易云 解密")
        root.geometry("780x600")
        root.minsize(660, 480)

        self.input_var = tk.StringVar()
        self.out_var = tk.StringVar()
        self.recursive_var = tk.BooleanVar(value=True)
        self.beep_var = tk.BooleanVar(value=True)

        self._build_ui()
        self._load_cfg()
        if HAVE_DND:
            self._enable_dnd()

        if not DEC_OK:
            self._append_log("依赖初始化失败: %s (请 pip install cryptography)" % IMPORT_ERR, "err")
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self._poll_queue()

    # ---------------- UI 构建
    def _build_ui(self):
        frm = ttk.Frame(self.root, padding=8)
        frm.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frm, text="输入(文件/文件夹, 可多个, 支持路径字符串):").grid(row=0, column=0, sticky="w", columnspan=3)
        self.in_entry = ttk.Entry(frm, textvariable=self.input_var)
        self.in_entry.grid(row=1, column=0, sticky="ew", padx=(0, 4))
        ttk.Button(frm, text="选择文件", command=self._pick_files).grid(row=1, column=1)
        ttk.Button(frm, text="选择文件夹", command=self._pick_dir).grid(row=1, column=2, padx=(4, 0))
        ttk.Button(frm, text="清空", command=lambda: self.input_var.set("")).grid(row=1, column=3, padx=(4, 0))

        ttk.Label(frm, text="输出(留空=自动: 文件同目录 / 文件夹旁同名_decoded):").grid(row=2, column=0, sticky="w", columnspan=3, pady=(8, 0))
        self.out_entry = ttk.Entry(frm, textvariable=self.out_var)
        self.out_entry.grid(row=3, column=0, sticky="ew", padx=(0, 4))
        ttk.Button(frm, text="选择输出文件夹", command=self._pick_out_dir).grid(row=3, column=1)
        ttk.Button(frm, text="选择输出文件", command=self._pick_out_file).grid(row=3, column=2, padx=(4, 0))

        opt = ttk.Frame(frm)
        opt.grid(row=4, column=0, columnspan=4, sticky="w", pady=6)
        ttk.Checkbutton(opt, text="递归处理子目录", variable=self.recursive_var).pack(side=tk.LEFT)
        ttk.Checkbutton(opt, text="完成后提示", variable=self.beep_var).pack(side=tk.LEFT, padx=12)

        ctl = ttk.Frame(frm)
        ctl.grid(row=5, column=0, columnspan=4, sticky="ew", pady=(0, 4))
        self.btn_start = ttk.Button(ctl, text="开始解密", command=self.on_start)
        self.btn_start.pack(side=tk.LEFT)
        self.btn_cancel = ttk.Button(ctl, text="取消", command=self.on_cancel, state=tk.DISABLED)
        self.btn_cancel.pack(side=tk.LEFT, padx=6)
        self.progress = ttk.Progressbar(ctl, mode="determinate")
        self.progress.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)
        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(ctl, textvariable=self.status_var).pack(side=tk.LEFT)

        logfrm = ttk.Frame(frm)
        logfrm.grid(row=6, column=0, columnspan=4, sticky="nsew")
        frm.rowconfigure(6, weight=1)
        frm.columnconfigure(0, weight=1)
        self.log = tk.Text(logfrm, height=14, wrap=tk.NONE, state=tk.DISABLED)
        sb = ttk.Scrollbar(logfrm, orient=tk.VERTICAL, command=self.log.yview)
        self.log.configure(yscrollcommand=sb.set)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.log.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        for tag, color in (("ok", "#0a7d0a"), ("err", "#c00000"), ("info", "#1a5aa8")):
            self.log.tag_configure(tag, foreground=color)

    def _enable_dnd(self):
        for w in (self.root, self.in_entry):
            try:
                w.drop_target_register(DND_FILES)
                w.dnd_bind("<<Drop>>", self._on_drop)
            except Exception:
                pass

    def _on_drop(self, event):
        try:
            paths = list(self.root.tk.splitlist(event.data))
        except Exception:
            paths = [event.data]
        self._add_inputs(paths)

    # ---------------- 选择回调
    def _pick_files(self):
        fs = filedialog.askopenfilenames(title="选择加密音乐文件",
            filetypes=[("加密音乐", "*.mflac *.mgg *.kgg *.ncm"), ("所有文件", "*.*")])
        if fs:
            self._add_inputs(fs)

    def _pick_dir(self):
        d = filedialog.askdirectory(title="选择包含加密音乐的文件夹")
        if d:
            self._add_inputs([d])

    def _pick_out_dir(self):
        d = filedialog.askdirectory(title="选择输出文件夹")
        if d:
            self.out_var.set(d)

    def _pick_out_file(self):
        f = filedialog.asksaveasfilename(title="选择输出文件",
            filetypes=[("音频", "*.flac *.mp3 *.ogg"), ("所有文件", "*.*")])
        if f:
            self.out_var.set(f)

    def _add_inputs(self, paths):
        cur = self.input_var.get().strip()
        lines = [l for l in cur.replace(";", "\n").splitlines() if l.strip()]
        for p in paths:
            if p.strip() and p.strip() not in lines:
                lines.append(p.strip())
        self.input_var.set("\n".join(lines))

    # ---------------- 任务执行
    def on_start(self):
        if self.worker and self.worker.is_alive():
            return
        inputs = parse_inputs(self.input_var.get())
        if not inputs:
            messagebox.showwarning("提示", "请先填写输入路径(文件或文件夹)")
            return
        out = self.out_var.get().strip().strip('"').strip() or None
        out_file = None
        out_root = None
        if out:
            # 判定用户给的是文件还是文件夹: 带扩展名且非目录视为输出文件
            if os.path.splitext(out)[1] and not os.path.isdir(out):
                out_file = os.path.abspath(out)
            else:
                out_root = os.path.abspath(out)

        tasks = collect_tasks(inputs, self.recursive_var.get())
        if not tasks:
            messagebox.showwarning("提示", "未找到支持的加密文件 (.mflac/.mgg/.kgg/.ncm)")
            return

        self.cancel_event.clear()
        self.btn_start.config(state=tk.DISABLED)
        self.btn_cancel.config(state=tk.NORMAL)
        self.progress.configure(maximum=len(tasks), value=0)
        self.status_var.set("0/%d" % len(tasks))
        self._append_log("== 开始解密 %d 个文件 ==" % len(tasks), "info")
        self.worker = threading.Thread(target=self._run_batch,
                                       args=(tasks, out_root, out_file), daemon=True)
        self.worker.start()

    def _run_batch(self, tasks, out_root, out_file):
        total, done = len(tasks), 0
        single = total == 1
        for src, rel, droot in tasks:
            if self.cancel_event.is_set():
                break
            self.msgq.put(("log", "→ %s" % src, "info"))
            try:
                d, b = self._resolve_output(src, rel, droot, out_root, out_file, single)
                os.makedirs(d, exist_ok=True)
                ext0 = os.path.splitext(src)[1].lower()
                if ext0 in QQ_EXTS:
                    oe = ".flac" if ext0 == ".mflac" else ".ogg"
                    out = os.path.join(d, b + oe)
                    ok, msg = qq_decrypt(src, out)
                    if ok:
                        self.msgq.put(("log", "✔ %s  ->  %s" % (os.path.basename(src), out), "ok"))
                    else:
                        self.msgq.put(("log", "✘ %s : %s" % (os.path.basename(src), msg), "err"))
                else:
                    data, ext, info = py_decrypt(src)
                    out = os.path.join(d, b + "." + ext)
                    with open(out, "wb") as f:
                        f.write(data)
                    extra = ("   [" + info + "]") if info else ""
                    self.msgq.put(("log", "✔ %s  ->  %s%s" % (os.path.basename(src), out, extra), "ok"))
            except Exception as e:
                self.msgq.put(("log", "✘ %s : %s" % (os.path.basename(src), e), "err"))
            done += 1
            self.msgq.put(("progress", done, total))
        self.msgq.put(("finish",))

    def _resolve_output(self, src, rel, droot, out_root, out_file, single):
        if out_file and single:
            d = os.path.dirname(out_file) or "."
            b = os.path.splitext(os.path.basename(out_file))[0]
            return d, b
        if out_root:
            d = out_root
        elif droot:
            d = droot
        else:
            d = os.path.dirname(src)
        sub = os.path.dirname(rel)
        if sub:
            d = os.path.join(d, sub)
        b = os.path.splitext(os.path.basename(src))[0]
        return d, b

    def on_cancel(self):
        self.cancel_event.set()
        self._append_log("== 已请求取消 ==", "info")

    # ---------------- 队列轮询
    def _poll_queue(self):
        try:
            while True:
                item = self.msgq.get_nowait()
                kind = item[0]
                if kind == "log":
                    _, text, tag = item
                    self._append_log(text, tag)
                elif kind == "progress":
                    _, done, total = item
                    self.progress.configure(value=done)
                    self.status_var.set("%d/%d" % (done, total))
                elif kind == "finish":
                    total = int(self.progress["maximum"])
                    done = int(self.progress["value"])
                    cancelled = self.cancel_event.is_set()
                    self.btn_start.config(state=tk.NORMAL)
                    self.btn_cancel.config(state=tk.DISABLED)
                    if cancelled:
                        self.status_var.set("已取消 (%d/%d)" % (done, total))
                        self._append_log("== 已取消, 完成 %d/%d ==" % (done, total), "info")
                    else:
                        self.status_var.set("完成 %d/%d" % (done, total))
                        self._append_log("== 全部完成: %d/%d 成功 ==" % (done, total), "info")
                        if self.beep_var.get():
                            winsound.MessageBeep(winsound.MB_ICONINFORMATION)
                            messagebox.showinfo("完成", "解密完成: %d/%d" % (done, total))
        except queue.Empty:
            pass
        self.root.after(100, self._poll_queue)

    def _append_log(self, text, tag="info"):
        self.log.configure(state=tk.NORMAL)
        self.log.insert(tk.END, text + "\n", tag)
        self.log.see(tk.END)
        self.log.configure(state=tk.DISABLED)

    # ---------------- 配置
    def _cfg(self):
        return {
            "input": self.input_var.get(),
            "output": self.out_var.get(),
            "recursive": self.recursive_var.get(),
            "beep": self.beep_var.get(),
        }

    def _load_cfg(self):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                c = json.load(f)
            self.input_var.set(c.get("input", ""))
            self.out_var.set(c.get("output", ""))
            self.recursive_var.set(c.get("recursive", True))
            self.beep_var.set(c.get("beep", True))
        except Exception:
            pass

    def on_close(self):
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(self._cfg(), f, ensure_ascii=False, indent=2)
        except Exception:
            pass
        self.root.destroy()


def main():
    root = TkinterDnD.Tk() if HAVE_DND else tk.Tk()
    app = MusicDecApp(root)
    if len(sys.argv) > 1:
        app._add_inputs(sys.argv[1:])
    root.mainloop()


if __name__ == "__main__":
    main()
