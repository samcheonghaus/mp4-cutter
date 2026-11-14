"""
MP4 Cutter - 심플한 무손실 MP4 자르기 프로그램
사용법: python mp4cutter.py [영상파일]   (exe 위에 영상 파일을 끌어다 놓아도 열립니다)
"""
import base64
import os
import sys
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import cutter_core as core

APP_NAME = "MP4 Cutter"
VERSION = "1.0.0"
PREVIEW_W, PREVIEW_H = 800, 450
TL_H = 46  # timeline height

BG = "#1e1f22"
PANEL = "#2b2d31"
FG = "#e6e6e6"
MUTED = "#9aa0a6"
ACCENT = "#4c8dff"
SEG = "#2fbf71"
INOUT = "#ffb020"


class App:
    def __init__(self, root, initial=None):
        self.root = root
        self.ffmpeg = None
        self.path = None
        self.info = None
        self.pos = 0.0
        self.in_t = None
        self.out_t = None
        self.segments = []
        self._frame_job = None
        self._frame_req = 0
        self._photo = None
        self._busy = False
        self._cancel = False

        root.title(f"{APP_NAME} {VERSION}")
        root.configure(bg=BG)
        root.minsize(860, 640)
        root.geometry("960x860")
        self._style()
        self._build()
        self._bind_keys()

        try:
            self.ffmpeg = core.find_ffmpeg()
        except FileNotFoundError as e:
            messagebox.showerror(APP_NAME, str(e))

        if initial and os.path.isfile(initial):
            root.after(100, lambda: self.open_file(initial))

    # ---------------- UI ----------------
    def _style(self):
        s = ttk.Style()
        try:
            s.theme_use("clam")
        except tk.TclError:
            pass
        font = ("Malgun Gothic", 10) if sys.platform == "win32" else ("TkDefaultFont", 10)
        self.font = font
        self.font_b = (font[0], 10, "bold")
        s.configure(".", background=BG, foreground=FG, font=font)
        s.configure("TFrame", background=BG)
        s.configure("Panel.TFrame", background=PANEL)
        s.configure("TLabel", background=BG, foreground=FG)
        s.configure("Panel.TLabel", background=PANEL, foreground=FG)
        s.configure("Muted.TLabel", background=BG, foreground=MUTED)
        s.configure("PMuted.TLabel", background=PANEL, foreground=MUTED)
        s.configure("Time.TLabel", background=BG, foreground=FG, font=("Consolas", 14, "bold"))
        s.configure("TButton", background="#3a3d43", foreground=FG, borderwidth=0, padding=(10, 5))
        s.map("TButton", background=[("active", "#4a4e55"), ("disabled", "#2a2c30")],
              foreground=[("disabled", "#666")])
        s.configure("Accent.TButton", background=ACCENT, foreground="white", font=self.font_b,
                    padding=(16, 8))
        s.map("Accent.TButton", background=[("active", "#6aa1ff"), ("disabled", "#2a2c30")])
        s.configure("TRadiobutton", background=PANEL, foreground=FG)
        s.map("TRadiobutton", background=[("active", PANEL)])
        s.configure("TRadiobutton", indicatorbackground="#16171a", indicatorforeground=ACCENT)
        s.map("TRadiobutton", indicatorbackground=[("selected", ACCENT)])
        s.configure("TEntry", fieldbackground="#16171a", foreground=FG, insertcolor=FG)
        s.configure("Horizontal.TProgressbar", background=ACCENT, troughcolor="#16171a")

    def _build(self):
        r = self.root
        pad = {"padx": 10}

        # top bar
        top = ttk.Frame(r)
        top.pack(fill="x", pady=(10, 6), **pad)
        ttk.Button(top, text="📂 영상 열기", command=self.choose_file).pack(side="left")
        self.lbl_file = ttk.Label(top, text="MP4 파일을 열어주세요  (Ctrl+O)", style="Muted.TLabel")
        self.lbl_file.pack(side="left", padx=10)

        # preview
        self.preview = tk.Label(r, bg="black", text="미리보기\n\n영상 파일을 열어주세요",
                                fg="#555", font=(self.font[0], 14))
        self.preview.bind("<Configure>", self._on_preview_resize)
        self._pv_size = (PREVIEW_W, PREVIEW_H)

        # timeline
        self.tl = tk.Canvas(r, height=TL_H, bg="#16171a", highlightthickness=0, cursor="hand2")
        self.tl.bind("<Button-1>", self._tl_click)
        self.tl.bind("<B1-Motion>", self._tl_click)
        self.tl.bind("<Configure>", lambda e: self._draw_timeline())

        # time + nav
        nav = ttk.Frame(r)
        self.lbl_time = ttk.Label(nav, text="00:00:00.000 / 00:00:00.000", style="Time.TLabel")
        self.lbl_time.pack(side="left")
        for txt, d in (("+10초", 10), ("+1초", 1), ("+1프레임", "f"),
                       ("-1프레임", "-f"), ("-1초", -1), ("-10초", -10)):
            ttk.Button(nav, text=txt,
                       command=lambda d=d: self.step(d)).pack(side="right", padx=2)

        # cut panel
        panel = ttk.Frame(r, style="Panel.TFrame", padding=10)

        row1 = ttk.Frame(panel, style="Panel.TFrame")
        row1.pack(fill="x")
        ttk.Label(row1, text="시작", style="Panel.TLabel").pack(side="left")
        self.ent_in = ttk.Entry(row1, width=14, font=("Consolas", 11))
        self.ent_in.pack(side="left", padx=4)
        self.ent_in.bind("<Return>", lambda e: self._entry_set("in"))
        self.ent_in.bind("<FocusOut>", lambda e: self._entry_set("in"))
        ttk.Button(row1, text="[ 현재 위치 (I)", command=self.set_in).pack(side="left")

        ttk.Label(row1, text="   끝", style="Panel.TLabel").pack(side="left")
        self.ent_out = ttk.Entry(row1, width=14, font=("Consolas", 11))
        self.ent_out.pack(side="left", padx=4)
        self.ent_out.bind("<Return>", lambda e: self._entry_set("out"))
        self.ent_out.bind("<FocusOut>", lambda e: self._entry_set("out"))
        ttk.Button(row1, text="현재 위치 ] (O)", command=self.set_out).pack(side="left")

        ttk.Button(row1, text="➕ 구간 추가 (A)", command=self.add_segment).pack(side="right")

        row2 = ttk.Frame(panel, style="Panel.TFrame")
        row2.pack(fill="x", pady=(10, 0))
        self.lst = tk.Listbox(row2, height=4, bg="#16171a", fg=FG, selectbackground=ACCENT,
                              highlightthickness=0, borderwidth=0, font=("Consolas", 10),
                              activestyle="none")
        self.lst.pack(side="left", fill="x", expand=True)
        self.lst.bind("<Double-Button-1>", self._jump_segment)
        btns = ttk.Frame(row2, style="Panel.TFrame")
        btns.pack(side="left", padx=(8, 0), fill="y")
        ttk.Button(btns, text="선택 삭제", command=self.del_segment).pack(fill="x")
        ttk.Button(btns, text="전체 삭제", command=self.clear_segments).pack(fill="x", pady=4)

        ttk.Label(panel, text="※ 구간을 추가하지 않으면 위의 시작~끝 한 구간만 저장합니다. "
                              "여러 구간을 추가하면 중간 부분을 잘라내고 이어 붙일 수 있습니다.",
                  style="PMuted.TLabel").pack(anchor="w", pady=(6, 0))

        # options
        opt = ttk.Frame(r, style="Panel.TFrame", padding=10)
        self.var_mode = tk.StringVar(value="copy")
        ttk.Label(opt, text="방식", style="Panel.TLabel", font=self.font_b).grid(row=0, column=0, sticky="w")
        ttk.Radiobutton(opt, text="무손실 빠른 자르기 (화질·용량 원본 그대로, 키프레임 기준으로 잘림)",
                        variable=self.var_mode, value="copy").grid(row=0, column=1, sticky="w", padx=8)
        ttk.Radiobutton(opt, text="정확한 자르기 (프레임 단위 정확, 재인코딩이라 조금 느림)",
                        variable=self.var_mode, value="precise").grid(row=1, column=1, sticky="w", padx=8)
        self.var_merge = tk.StringVar(value="merge")
        ttk.Label(opt, text="여러 구간", style="Panel.TLabel", font=self.font_b).grid(
            row=2, column=0, sticky="w", pady=(6, 0))
        f = ttk.Frame(opt, style="Panel.TFrame")
        f.grid(row=2, column=1, sticky="w", padx=8, pady=(6, 0))
        ttk.Radiobutton(f, text="하나로 이어 붙이기", variable=self.var_merge,
                        value="merge").pack(side="left")
        ttk.Radiobutton(f, text="각각 따로 저장", variable=self.var_merge,
                        value="split").pack(side="left", padx=16)

        # export
        bottom = ttk.Frame(r)
        self.btn_save = ttk.Button(bottom, text="💾 저장하기", style="Accent.TButton",
                                   command=self.export)
        self.btn_save.pack(side="right")
        self.btn_cancel = ttk.Button(bottom, text="취소", command=self._do_cancel)
        self.prog = ttk.Progressbar(bottom, mode="determinate", maximum=1000)
        self.prog.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.lbl_status = ttk.Label(r, text="단축키: ←/→ 1초 · Shift+←/→ 1프레임 · "
                                            "PgUp/PgDn 10초 · Home/End · I 시작 · O 끝 · A 구간추가",
                                    style="Muted.TLabel")
        # bottom-up packing so the preview (packed last) is the one that shrinks
        self.lbl_status.pack(side="bottom", anchor="w", padx=10, pady=(0, 8))
        bottom.pack(side="bottom", fill="x", pady=(2, 4), **pad)
        opt.pack(side="bottom", fill="x", pady=(0, 6), **pad)
        panel.pack(side="bottom", fill="x", pady=(4, 6), **pad)
        nav.pack(side="bottom", fill="x", pady=6, **pad)
        self.tl.pack(side="bottom", fill="x", pady=(8, 0), **pad)
        self.preview.pack(fill="both", expand=True, **pad)

    def _bind_keys(self):
        r = self.root
        r.bind("<Control-o>", lambda e: self.choose_file())
        r.bind("<Control-s>", lambda e: self.export())

        def k(fn):
            def h(e):
                if isinstance(r.focus_get(), (tk.Entry, ttk.Entry)):
                    return
                fn()
                return "break"
            return h

        r.bind("<Left>", k(lambda: self.step(-1)))
        r.bind("<Right>", k(lambda: self.step(1)))
        r.bind("<Shift-Left>", k(lambda: self.step("-f")))
        r.bind("<Shift-Right>", k(lambda: self.step("f")))
        r.bind("<Prior>", k(lambda: self.step(-10)))
        r.bind("<Next>", k(lambda: self.step(10)))
        r.bind("<Home>", k(lambda: self.seek(0)))
        r.bind("<End>", k(lambda: self.seek(self.duration)))
        for key, fn in (("i", self.set_in), ("o", self.set_out), ("a", self.add_segment)):
            r.bind(f"<KeyPress-{key}>", k(fn))
            r.bind(f"<KeyPress-{key.upper()}>", k(fn))
        self.preview.bind("<Button-1>", lambda e: self.root.focus_set())

    # ---------------- file ----------------
    @property
    def duration(self):
        return self.info["duration"] if self.info else 0.0

    def choose_file(self):
        if self._busy:
            return
        p = filedialog.askopenfilename(
            title="영상 열기",
            filetypes=[("동영상", "*.mp4 *.mov *.m4v *.mkv *.avi *.webm *.ts"), ("모든 파일", "*.*")])
        if p:
            self.open_file(p)

    def open_file(self, path):
        if not self.ffmpeg:
            return
        try:
            info = core.probe(self.ffmpeg, path)
        except Exception as e:
            messagebox.showerror(APP_NAME, f"파일을 열 수 없습니다.\n\n{e}")
            return
        self.path, self.info = path, info
        size = os.path.getsize(path) / (1024 * 1024)
        detail = f"{info['width']}x{info['height']}"
        if info["fps"]:
            detail += f" · {info['fps']:g}fps"
        if info["vcodec"]:
            detail += f" · {info['vcodec']}"
        detail += f" · {size:,.1f} MB"
        self.lbl_file.configure(text=f"{os.path.basename(path)}   ({detail})", style="TLabel")
        self.segments.clear()
        self._refresh_list()
        self.in_t, self.out_t = 0.0, info["duration"]
        self._sync_entries()
        self.seek(0)
        self.root.title(f"{APP_NAME} - {os.path.basename(path)}")

    # ---------------- position ----------------
    def seek(self, t):
        if not self.info:
            return
        self.pos = max(0.0, min(t, self.duration))
        self.lbl_time.configure(text=f"{core.fmt_time(self.pos)} / {core.fmt_time(self.duration)}")
        self._draw_timeline()
        if self._frame_job:
            self.root.after_cancel(self._frame_job)
        self._frame_job = self.root.after(60, self._load_frame)

    def step(self, d):
        if not self.info:
            return
        if d in ("f", "-f"):
            fr = 1.0 / (self.info["fps"] or 30)
            d = fr if d == "f" else -fr
        self.seek(self.pos + d)

    def _load_frame(self):
        self._frame_job = None
        self._frame_req += 1
        req, t, path = self._frame_req, min(self.pos, max(self.duration - 0.05, 0)), self.path

        def work():
            data = core.grab_frame(self.ffmpeg, path, t, *self._pv_size)
            self.root.after(0, lambda: self._show_frame(req, data))
        threading.Thread(target=work, daemon=True).start()

    def _on_preview_resize(self, e):
        size = (max(e.width - 4, 160), max(e.height - 4, 90))
        if abs(size[0] - self._pv_size[0]) > 8 or abs(size[1] - self._pv_size[1]) > 8:
            self._pv_size = size
            if self.info:
                if self._frame_job:
                    self.root.after_cancel(self._frame_job)
                self._frame_job = self.root.after(200, self._load_frame)

    def _show_frame(self, req, data):
        if req != self._frame_req or not data:
            return
        self._photo = tk.PhotoImage(data=base64.b64encode(data))
        self.preview.configure(image=self._photo, text="")

    # ---------------- timeline ----------------
    def _x(self, t):
        w = self.tl.winfo_width() - 20
        return 10 + (t / self.duration) * w if self.duration else 10

    def _tl_click(self, e):
        if not self.info:
            return
        w = self.tl.winfo_width() - 20
        self.seek((e.x - 10) / w * self.duration)

    def _draw_timeline(self):
        c = self.tl
        c.delete("all")
        w = c.winfo_width()
        c.create_rectangle(10, 18, w - 10, 30, fill="#33363c", outline="")
        if not self.info:
            return
        # tick labels
        n = 8
        for i in range(n + 1):
            t = self.duration * i / n
            x = self._x(t)
            c.create_line(x, 30, x, 35, fill="#555")
            anchor = "w" if i == 0 else ("e" if i == n else "center")
            c.create_text(x, 41, text=core.fmt_time(t)[:8], fill="#777", font=("Consolas", 7),
                          anchor=anchor)
        for s, e in self.segments:
            c.create_rectangle(self._x(s), 18, self._x(e), 30, fill=SEG, outline="")
        if self.in_t is not None and self.out_t is not None and self.out_t > self.in_t:
            c.create_rectangle(self._x(self.in_t), 15, self._x(self.out_t), 33,
                               outline=INOUT, width=2)
        x = self._x(self.pos)
        c.create_line(x, 4, x, 36, fill=ACCENT, width=2)
        c.create_polygon(x - 6, 2, x + 6, 2, x, 10, fill=ACCENT, outline="")

    # ---------------- in/out & segments ----------------
    def _sync_entries(self):
        for ent, v in ((self.ent_in, self.in_t), (self.ent_out, self.out_t)):
            ent.delete(0, "end")
            if v is not None:
                ent.insert(0, core.fmt_time(v))
        self._draw_timeline()

    def _entry_set(self, which):
        if not self.info:
            return
        ent = self.ent_in if which == "in" else self.ent_out
        try:
            v = max(0.0, min(core.parse_time(ent.get()), self.duration))
        except ValueError:
            self._sync_entries()
            return
        if which == "in":
            self.in_t = v
        else:
            self.out_t = v
        self._sync_entries()

    def set_in(self):
        if self.info:
            self.in_t = self.pos
            if self.out_t is not None and self.out_t <= self.in_t:
                self.out_t = self.duration
            self._sync_entries()

    def set_out(self):
        if self.info:
            self.out_t = self.pos
            if self.in_t is not None and self.in_t >= self.out_t:
                self.in_t = 0.0
            self._sync_entries()

    def add_segment(self):
        if not self.info:
            return
        self._entry_set("in")
        self._entry_set("out")
        if self.in_t is None or self.out_t is None or self.out_t - self.in_t < 0.05:
            messagebox.showwarning(APP_NAME, "끝 시간이 시작 시간보다 뒤여야 합니다.")
            return
        self.segments.append((self.in_t, self.out_t))
        self.segments.sort()
        self._refresh_list()
        # next segment starts where this one ended
        self.in_t, self.out_t = self.out_t, self.duration
        self._sync_entries()

    def del_segment(self):
        for i in reversed(self.lst.curselection()):
            del self.segments[i]
        self._refresh_list()

    def clear_segments(self):
        self.segments.clear()
        self._refresh_list()

    def _jump_segment(self, _):
        sel = self.lst.curselection()
        if sel:
            self.seek(self.segments[sel[0]][0])

    def _refresh_list(self):
        self.lst.delete(0, "end")
        total = 0.0
        for i, (s, e) in enumerate(self.segments, 1):
            total += e - s
            self.lst.insert("end", f" {i:2d}.  {core.fmt_time(s)}  →  {core.fmt_time(e)}"
                                   f"    ({core.fmt_time(e - s)})")
        if self.segments:
            self.lbl_status.configure(text=f"구간 {len(self.segments)}개 · 합계 {core.fmt_time(total)}")
        self._draw_timeline()

    # ---------------- export ----------------
    def export(self):
        if self._busy or not self.info:
            return
        self._entry_set("in")
        self._entry_set("out")
        segs = list(self.segments)
        if not segs:
            if self.in_t is None or self.out_t is None or self.out_t - self.in_t < 0.05:
                messagebox.showwarning(APP_NAME, "저장할 구간을 지정하세요.")
                return
            segs = [(self.in_t, self.out_t)]

        root, _ = os.path.splitext(self.path)
        n = 1
        while os.path.exists(f"{root}_cut{n:02d}.mp4"):
            n += 1
        out = filedialog.asksaveasfilename(
            title="저장할 파일", defaultextension=".mp4",
            initialdir=os.path.dirname(self.path),
            initialfile=os.path.basename(f"{root}_cut{n:02d}.mp4"),
            filetypes=[("MP4", "*.mp4")])
        if not out:
            return
        if os.path.abspath(out) == os.path.abspath(self.path):
            messagebox.showerror(APP_NAME, "원본 파일에 덮어쓸 수 없습니다. 다른 이름을 지정하세요.")
            return

        precise = self.var_mode.get() == "precise"
        merge = self.var_merge.get() == "merge"
        self._set_busy(True)

        def progress(f):
            self.root.after(0, lambda: self.prog.configure(value=f * 1000))

        def work():
            try:
                files = core.cut(self.ffmpeg, self.path, segs, out, precise=precise, merge=merge,
                                 on_progress=progress, cancel=lambda: self._cancel)
                self.root.after(0, lambda: self._done(files, None))
            except Exception as e:
                self.root.after(0, lambda e=e: self._done(None, e))
        threading.Thread(target=work, daemon=True).start()

    def _set_busy(self, busy):
        self._busy, self._cancel = busy, False
        self.btn_save.configure(state="disabled" if busy else "normal")
        if busy:
            self.prog.configure(value=0)
            self.btn_cancel.pack(side="right", padx=(0, 8))
            self.lbl_status.configure(text="저장 중...")
        else:
            self.btn_cancel.pack_forget()

    def _do_cancel(self):
        self._cancel = True

    def _done(self, files, err):
        self._set_busy(False)
        if err:
            self.prog.configure(value=0)
            if isinstance(err, InterruptedError):
                self.lbl_status.configure(text="취소되었습니다.")
            else:
                self.lbl_status.configure(text="저장 실패")
                messagebox.showerror(APP_NAME, str(err))
            return
        src = os.path.getsize(self.path) / (1024 * 1024)
        lines = [f"{os.path.basename(f)}  ({os.path.getsize(f) / (1024 * 1024):,.1f} MB)" for f in files]
        self.lbl_status.configure(text=f"완료: {', '.join(os.path.basename(f) for f in files)}")
        if messagebox.askyesno(APP_NAME, "저장 완료!\n\n" + "\n".join(lines) +
                               f"\n\n(원본 {src:,.1f} MB)\n\n폴더를 열까요?"):
            self._open_folder(files[0])

    @staticmethod
    def _open_folder(path):
        try:
            if sys.platform == "win32":
                import subprocess
                subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
            elif sys.platform == "darwin":
                import subprocess
                subprocess.Popen(["open", "-R", path])
            else:
                import subprocess
                subprocess.Popen(["xdg-open", os.path.dirname(path)])
        except Exception:
            pass


def main():
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)  # 선명한 글씨 (고해상도 모니터)
        except Exception:
            pass
    root = tk.Tk()
    App(root, sys.argv[1] if len(sys.argv) > 1 else None)
    root.mainloop()


if __name__ == "__main__":
    main()
