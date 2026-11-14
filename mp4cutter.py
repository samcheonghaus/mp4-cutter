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
VERSION = "1.1.0"
PREVIEW_W, PREVIEW_H = 800, 450
TL_H = 46  # timeline height

BG = "#1e1f22"
PANEL = "#2b2d31"
FG = "#e6e6e6"
MUTED = "#9aa0a6"
ACCENT = "#4c8dff"
SEG = "#2f9e63"
INOUT = "#ffb020"
CUT = "#e5484d"


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
        self._refresh_list()

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
        s.configure("Time.TLabel", background=BG, foreground=FG, font=("Consolas", 12, "bold"))
        s.configure("TButton", background="#3a3d43", foreground=FG, borderwidth=0, padding=(10, 5))
        s.map("TButton", background=[("active", "#4a4e55"), ("disabled", "#2a2c30")],
              foreground=[("disabled", "#666")])
        s.configure("Nav.TButton", padding=(6, 5))
        s.configure("Cut.TButton", background=CUT, foreground="white", font=self.font_b)
        s.map("Cut.TButton", background=[("active", "#f06b6f")])
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
            ttk.Button(nav, text=txt, style="Nav.TButton",
                       command=lambda d=d: self.step(d)).pack(side="right", padx=1)

        # cut panel (버릴 구간 지정)
        panel = ttk.Frame(r, style="Panel.TFrame", padding=10)

        row1 = ttk.Frame(panel, style="Panel.TFrame")
        row1.pack(fill="x")
        ttk.Label(row1, text="버릴 구간", style="Panel.TLabel", font=self.font_b,
                  foreground=CUT).pack(side="left", padx=(0, 10))
        ttk.Button(row1, text="① 여기부터 버리기 (S)", command=self.set_in).pack(side="left")
        self.ent_in = ttk.Entry(row1, width=13, font=("Consolas", 11))
        self.ent_in.pack(side="left", padx=(4, 12))
        self.ent_in.bind("<Return>", lambda e: self._entry_set("in"))
        self.ent_in.bind("<FocusOut>", lambda e: self._entry_set("in"))
        ttk.Button(row1, text="② 여기까지 버리기 (E)", command=self.set_out).pack(side="left")
        self.ent_out = ttk.Entry(row1, width=13, font=("Consolas", 11))
        self.ent_out.pack(side="left", padx=4)
        self.ent_out.bind("<Return>", lambda e: self._entry_set("out"))
        self.ent_out.bind("<FocusOut>", lambda e: self._entry_set("out"))
        ttk.Button(row1, text="✂ 잘라내기 (X)", style="Cut.TButton",
                   command=self.add_segment).pack(side="right")

        row2 = ttk.Frame(panel, style="Panel.TFrame")
        row2.pack(fill="x", pady=(10, 0))
        self.lst = tk.Listbox(row2, height=4, bg="#16171a", fg=FG, selectbackground=ACCENT,
                              highlightthickness=0, borderwidth=0, font=("Consolas", 10),
                              activestyle="none")
        self.lst.pack(side="left", fill="x", expand=True)
        self.lst.bind("<Double-Button-1>", self._jump_segment)
        btns = ttk.Frame(row2, style="Panel.TFrame")
        btns.pack(side="left", padx=(8, 0), fill="y")
        ttk.Button(btns, text="선택 되돌리기", command=self.del_segment).pack(fill="x")
        ttk.Button(btns, text="전체 되돌리기", command=self.clear_segments).pack(fill="x", pady=4)

        self.lbl_hint = ttk.Label(panel, text="", style="PMuted.TLabel")
        self.lbl_hint.pack(anchor="w", pady=(6, 0))

        # options
        opt = ttk.Frame(r, style="Panel.TFrame", padding=10)
        self.var_mode = tk.StringVar(value="copy")
        ttk.Label(opt, text="방식", style="Panel.TLabel", font=self.font_b).grid(row=0, column=0, sticky="w")
        ttk.Radiobutton(opt, text="빠르게 (화질·용량 원본 그대로, 자른 위치가 1초 정도 어긋날 수 있음)",
                        variable=self.var_mode, value="copy").grid(row=0, column=1, sticky="w", padx=8)
        ttk.Radiobutton(opt, text="정확하게 (프레임 단위로 정확, 저장이 조금 느림)",
                        variable=self.var_mode, value="precise").grid(row=1, column=1, sticky="w", padx=8)

        # export
        bottom = ttk.Frame(r)
        self.btn_save = ttk.Button(bottom, text="💾 저장하기", style="Accent.TButton",
                                   command=self.export)
        self.btn_save.pack(side="right")
        self.btn_cancel = ttk.Button(bottom, text="취소", command=self._do_cancel)
        self.prog = ttk.Progressbar(bottom, mode="determinate", maximum=1000)
        self.prog.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.lbl_status = ttk.Label(r, text="단축키: ←/→ 1초 · Shift+←/→ 1프레임 · "
                                            "PgUp/PgDn 10초 · S 여기부터 버리기 · E 여기까지 버리기 · X 잘라내기",
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
        for key, fn in (("s", self.set_in), ("e", self.set_out), ("x", self.add_segment),
                        ("i", self.set_in), ("o", self.set_out)):
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
        self.in_t = self.out_t = None
        self._refresh_list()
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
        # 남는 부분 = 초록, 버린 부분 = 빨강, 선택 중인 버릴 구간 = 주황
        c.create_rectangle(10, 18, w - 10, 30, fill=SEG, outline="")
        n = 8
        for i in range(n + 1):
            t = self.duration * i / n
            x = self._x(t)
            c.create_line(x, 30, x, 35, fill="#555")
            anchor = "w" if i == 0 else ("e" if i == n else "center")
            c.create_text(x, 41, text=core.fmt_time(t)[:8], fill="#777", font=("Consolas", 7),
                          anchor=anchor)
        for s, e in self.segments:
            c.create_rectangle(self._x(s), 18, self._x(e), 30, fill=CUT, outline="")
        if self._pending():
            x1, x2 = self._x(self.in_t), self._x(self.out_t)
            c.create_rectangle(x1, 18, x2, 30, fill=INOUT, outline="", stipple="gray50")
            c.create_rectangle(x1, 15, x2, 33, outline=INOUT, width=2)
        x = self._x(self.pos)
        c.create_line(x, 4, x, 36, fill=ACCENT, width=2)
        c.create_polygon(x - 6, 2, x + 6, 2, x, 10, fill=ACCENT, outline="")

    # ---------------- 버릴 구간 ----------------
    def _pending(self):
        return (self.in_t is not None and self.out_t is not None
                and self.out_t - self.in_t >= 0.05)

    def _all_cuts(self):
        cuts = list(self.segments)
        if self._pending():
            cuts.append((self.in_t, self.out_t))
        return cuts

    def _kept(self):
        """버릴 구간들을 뺀 나머지(남길 구간) 목록"""
        cuts = sorted(self._all_cuts())
        merged = []
        for s, e in cuts:
            if merged and s <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], e)
            else:
                merged.append([s, e])
        kept, t = [], 0.0
        for s, e in merged:
            if s - t >= 0.05:
                kept.append((t, s))
            t = max(t, e)
        if self.duration - t >= 0.05:
            kept.append((t, self.duration))
        return kept

    def _sync_entries(self):
        for ent, v in ((self.ent_in, self.in_t), (self.ent_out, self.out_t)):
            ent.delete(0, "end")
            if v is not None:
                ent.insert(0, core.fmt_time(v))
        self._update_hint()
        self._draw_timeline()

    def _update_hint(self):
        if not self.info:
            self.lbl_hint.configure(text="")
            return
        kept = sum(e - s for s, e in self._kept())
        msg = f"남는 길이 {core.fmt_time(kept)}  (원본 {core.fmt_time(self.duration)})"
        if self._pending():
            msg += "   ·   주황색 = 버릴 부분  →  [✂ 잘라내기] 또는 바로 [저장하기]"
        elif not self.segments:
            msg += "   ·   버릴 장면으로 이동해서 [① 여기부터 버리기]를 누르세요"
        self.lbl_hint.configure(text=msg)

    def _entry_set(self, which):
        if not self.info:
            return
        ent = self.ent_in if which == "in" else self.ent_out
        if not ent.get().strip():
            return
        try:
            v = max(0.0, min(core.parse_time(ent.get()), self.duration))
        except ValueError:
            self._sync_entries()
            return
        if which == "in":
            self.in_t = v
            if self.out_t is None or self.out_t <= v:
                self.out_t = self.duration
        else:
            self.out_t = v
            if self.in_t is None or self.in_t >= v:
                self.in_t = 0.0
        self._sync_entries()

    def set_in(self):
        """① 여기부터 버리기 (끝을 안 정하면 영상 끝까지)"""
        if self.info:
            self.in_t = self.pos
            if self.out_t is None or self.out_t <= self.in_t:
                self.out_t = self.duration
            self._sync_entries()

    def set_out(self):
        """② 여기까지 버리기 (시작을 안 정하면 영상 처음부터)"""
        if self.info:
            self.out_t = self.pos
            if self.in_t is None or self.in_t >= self.out_t:
                self.in_t = 0.0
            self._sync_entries()

    def add_segment(self):
        """✂ 잘라내기: 선택한 버릴 구간을 목록에 넣음"""
        if not self.info:
            return
        if not self._pending():
            messagebox.showinfo(APP_NAME, "먼저 [① 여기부터 버리기] 또는 [② 여기까지 버리기]로 "
                                          "버릴 부분을 선택하세요.")
            return
        self.segments.append((self.in_t, self.out_t))
        self.segments.sort()
        self.in_t = self.out_t = None
        self._refresh_list()
        self._sync_entries()

    def del_segment(self):
        for i in reversed(self.lst.curselection()):
            del self.segments[i]
        self._refresh_list()

    def clear_segments(self):
        self.segments.clear()
        self.in_t = self.out_t = None
        self._refresh_list()
        self._sync_entries()

    def _jump_segment(self, _):
        sel = self.lst.curselection()
        if sel:
            self.seek(self.segments[sel[0]][0])

    def _refresh_list(self):
        self.lst.delete(0, "end")
        for i, (s, e) in enumerate(self.segments, 1):
            self.lst.insert("end", f" ✂ {i:2d}.  {core.fmt_time(s)}  →  {core.fmt_time(e)}"
                                   f"    ({core.fmt_time(e - s)} 버림)")
        if not self.segments:
            self.lst.insert("end", "  잘라낸 부분이 여기에 표시됩니다")
            self.lst.itemconfig(0, foreground="#666")
        self._update_hint()
        self._draw_timeline()

    # ---------------- export ----------------
    def export(self):
        if self._busy or not self.info:
            return
        self._entry_set("in")
        self._entry_set("out")
        if not self._all_cuts():
            messagebox.showwarning(APP_NAME, "버릴 부분을 먼저 지정하세요.\n\n"
                                             "버릴 장면으로 이동 → [① 여기부터 버리기] → 저장하기")
            return
        segs = self._kept()
        if not segs:
            messagebox.showwarning(APP_NAME, "전부 버리면 남는 영상이 없습니다.")
            return

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
        self._set_busy(True)

        def progress(f):
            self.root.after(0, lambda: self.prog.configure(value=f * 1000))

        def work():
            try:
                files = core.cut(self.ffmpeg, self.path, segs, out, precise=precise, merge=True,
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
