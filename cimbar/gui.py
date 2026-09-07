"""Drag-and-drop desktop UI for cimbar (pure Python, tkinter).

Send tab:    drop a file (zip or anything) -> cimbar frames + animated GIF.
Receive tab: drop the frame PNGs (or their folder) -> the original file back.

Drag-and-drop uses ``tkinterdnd2`` when installed; otherwise use the Browse
buttons. Run with:  ``python -m cimbar gui``  or  ``python -m cimbar.gui``.
"""

import os
import sys
import glob
import queue
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from PIL import Image, ImageTk

from . import encode as encode_bytes, Decoder

try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
    _HAS_DND = True
except Exception:  # noqa: BLE001
    _HAS_DND = False

BG = "#11141a"
PANEL = "#1b2029"
ACCENT = "#2dd4bf"
DROP_IDLE = "#232a36"
DROP_HOT = "#2b3646"
FG = "#e6edf3"
MUTED = "#8b98a5"


def _open_folder(path):
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)  # noqa: S606
        elif sys.platform == "darwin":
            os.system("open '%s'" % path)
        else:
            os.system("xdg-open '%s'" % path)
    except Exception:  # noqa: BLE001
        pass


class DropZone(tk.Frame):
    """A labelled area that accepts dropped files (or click-to-browse)."""

    def __init__(self, master, text, on_files, browse_cmd):
        super().__init__(master, bg=DROP_IDLE, highlightbackground=MUTED,
                         highlightthickness=2, bd=0)
        self._on_files = on_files
        self.label = tk.Label(self, text=text, bg=DROP_IDLE, fg=MUTED,
                              font=("Segoe UI", 12), justify="center")
        self.label.pack(expand=True, fill="both", padx=20, pady=24)
        self.browse = tk.Button(self, text="Browse…", command=browse_cmd,
                                bg=PANEL, fg=FG, activebackground=ACCENT,
                                relief="flat", font=("Segoe UI", 10), cursor="hand2")
        self.browse.pack(pady=(0, 16))
        for w in (self, self.label):
            if _HAS_DND:
                w.drop_target_register(DND_FILES)
                w.dnd_bind("<<Drop>>", self._on_drop)
                w.dnd_bind("<<DropEnter>>", lambda e: self._hot(True))
                w.dnd_bind("<<DropLeave>>", lambda e: self._hot(False))

    def _hot(self, on):
        c = DROP_HOT if on else DROP_IDLE
        self.config(bg=c)
        self.label.config(bg=c)

    def _on_drop(self, event):
        self._hot(False)
        paths = list(self.tk.splitlist(event.data))
        paths = [p for p in paths if os.path.exists(p)]
        if paths:
            self._on_files(paths)


class CimbarApp:
    def __init__(self, root):
        self.root = root
        self.q = queue.Queue()
        self.preview_imgs = []
        self._anim_idx = 0
        self._anim_job = None

        root.title("cimbar — air-gapped file transfer")
        root.geometry("560x620")
        root.configure(bg=BG)
        root.minsize(520, 560)

        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", background=PANEL, foreground=MUTED,
                        padding=(18, 8), font=("Segoe UI", 10, "bold"))
        style.map("TNotebook.Tab", background=[("selected", BG)],
                  foreground=[("selected", ACCENT)])

        nb = ttk.Notebook(root)
        nb.pack(fill="both", expand=True, padx=12, pady=12)
        self.send_tab = tk.Frame(nb, bg=BG)
        self.recv_tab = tk.Frame(nb, bg=BG)
        nb.add(self.send_tab, text="  Send  ")
        nb.add(self.recv_tab, text="  Receive  ")

        self._build_send()
        self._build_recv()

        if not _HAS_DND:
            tk.Label(root, text="tip: install 'tkinterdnd2' to enable drag-and-drop",
                     bg=BG, fg=MUTED, font=("Segoe UI", 8)).pack(pady=(0, 6))

        self.root.after(80, self._pump)

    # ---------------- Send ----------------
    def _build_send(self):
        t = self.send_tab
        self.send_drop = DropZone(
            t, "Drop a file here to encode\n(zip, pdf, anything)",
            self._encode_files, self._browse_encode)
        self.send_drop.pack(fill="x", padx=8, pady=(8, 10))

        opts = tk.Frame(t, bg=BG)
        opts.pack(fill="x", padx=8)
        tk.Label(opts, text="GIF fps:", bg=BG, fg=MUTED,
                 font=("Segoe UI", 9)).pack(side="left")
        self.fps = tk.IntVar(value=15)
        tk.Spinbox(opts, from_=1, to=60, width=4, textvariable=self.fps,
                   font=("Segoe UI", 9)).pack(side="left", padx=(6, 0))

        self.send_status = tk.Label(t, text="", bg=BG, fg=FG,
                                    font=("Segoe UI", 10), wraplength=500, justify="left")
        self.send_status.pack(fill="x", padx=8, pady=(10, 4))
        self.send_bar = ttk.Progressbar(t, mode="indeterminate")

        self.preview = tk.Label(t, bg=PANEL)
        self.preview.pack(pady=8)
        self.send_open = tk.Button(t, text="Open output folder", state="disabled",
                                   command=lambda: _open_folder(self._last_out),
                                   bg=PANEL, fg=FG, relief="flat",
                                   font=("Segoe UI", 10), cursor="hand2")
        self.send_open.pack()
        self._last_out = None

    def _browse_encode(self):
        p = filedialog.askopenfilename(title="Choose a file to encode")
        if p:
            self._encode_files([p])

    def _encode_files(self, paths):
        path = paths[0]
        outdir = os.path.join(os.path.dirname(os.path.abspath(path)),
                              os.path.splitext(os.path.basename(path))[0] + "_cimbar")
        self._set_busy(self.send_bar, True)
        self.send_status.config(text="Encoding %s…" % os.path.basename(path))
        self.send_open.config(state="disabled")
        self._stop_anim()
        threading.Thread(target=self._encode_worker,
                         args=(path, outdir, self.fps.get()), daemon=True).start()

    def _encode_worker(self, path, outdir, fps):
        try:
            with open(path, "rb") as f:
                data = f.read()
            name = os.path.basename(path)
            frames = encode_bytes(data, name)
            os.makedirs(outdir, exist_ok=True)
            for i, im in enumerate(frames):
                im.save(os.path.join(outdir, "frame_%04d.png" % i))
            gif = os.path.join(outdir, os.path.splitext(name)[0] + ".gif")
            frames[0].save(gif, save_all=True, append_images=frames[1:],
                           duration=int(1000 / max(1, fps)), loop=0)
            self.q.put(("encoded", {"path": path, "n": len(frames),
                                    "outdir": outdir, "bytes": len(data),
                                    "frames": frames}))
        except Exception as exc:  # noqa: BLE001
            self.q.put(("error", ("Send", str(exc))))

    # ---------------- Receive ----------------
    def _build_recv(self):
        t = self.recv_tab
        self.recv_drop = DropZone(
            t, "Drop the frame PNGs or their folder here",
            self._decode_files, self._browse_decode)
        self.recv_drop.pack(fill="x", padx=8, pady=(8, 10))

        self.recv_status = tk.Label(t, text="", bg=BG, fg=FG,
                                    font=("Segoe UI", 10), wraplength=500, justify="left")
        self.recv_status.pack(fill="x", padx=8, pady=(10, 4))
        self.recv_bar = ttk.Progressbar(t, mode="indeterminate")
        self.recv_open = tk.Button(t, text="Open output folder", state="disabled",
                                   command=lambda: _open_folder(self._last_recv_out),
                                   bg=PANEL, fg=FG, relief="flat",
                                   font=("Segoe UI", 10), cursor="hand2")
        self.recv_open.pack(pady=6)
        self._last_recv_out = None

    def _browse_decode(self):
        ps = filedialog.askopenfilenames(
            title="Choose frame images", filetypes=[("PNG frames", "*.png")])
        if ps:
            self._decode_files(list(ps))

    def _collect_pngs(self, paths):
        files = []
        for p in paths:
            if os.path.isdir(p):
                files += sorted(glob.glob(os.path.join(p, "*.png")))
            elif p.lower().endswith(".png"):
                files.append(p)
        return files

    def _decode_files(self, paths):
        files = self._collect_pngs(paths)
        if not files:
            messagebox.showwarning("cimbar", "No PNG frames found in what you dropped.")
            return
        outdir = os.path.join(os.path.dirname(os.path.abspath(files[0])), "decoded")
        self._set_busy(self.recv_bar, True)
        self.recv_status.config(text="Decoding %d frame(s)…" % len(files))
        self.recv_open.config(state="disabled")
        threading.Thread(target=self._decode_worker,
                         args=(files, outdir), daemon=True).start()

    def _decode_worker(self, files, outdir):
        try:
            dec = Decoder()
            for f in files:
                if dec.add(f):
                    break
            if not dec.complete():
                self.q.put(("recv_incomplete",
                            {"missing": dec.missing(), "read": dec.frames_read}))
                return
            name, data = dec.result()
            os.makedirs(outdir, exist_ok=True)
            outpath = os.path.join(outdir, os.path.basename(name) or "output.bin")
            with open(outpath, "wb") as fh:
                fh.write(data)
            self.q.put(("decoded", {"outpath": outpath, "bytes": len(data),
                                    "outdir": outdir, "read": dec.frames_read,
                                    "failed": dec.frames_failed}))
        except Exception as exc:  # noqa: BLE001
            self.q.put(("error", ("Receive", str(exc))))

    # ---------------- helpers / event pump ----------------
    def _set_busy(self, bar, on):
        if on:
            bar.pack(fill="x", padx=8, pady=6)
            bar.start(12)
        else:
            bar.stop()
            bar.pack_forget()

    def _pump(self):
        try:
            while True:
                kind, payload = self.q.get_nowait()
                self._handle(kind, payload)
        except queue.Empty:
            pass
        self.root.after(80, self._pump)

    def _handle(self, kind, payload):
        if kind == "encoded":
            self._set_busy(self.send_bar, False)
            self._last_out = payload["outdir"]
            self.send_status.config(
                text="✓ %s (%d bytes) → %d frame(s)\n%s" % (
                    os.path.basename(payload["path"]), payload["bytes"],
                    payload["n"], payload["outdir"]))
            self.send_open.config(state="normal")
            self._start_anim(payload["frames"])
        elif kind == "decoded":
            self._set_busy(self.recv_bar, False)
            self._last_recv_out = payload["outdir"]
            self.recv_status.config(
                text="✓ recovered %d bytes → %s\n(%d frames read, %d failed)" % (
                    payload["bytes"], payload["outpath"],
                    payload["read"], payload["failed"]))
            self.recv_open.config(state="normal")
        elif kind == "recv_incomplete":
            self._set_busy(self.recv_bar, False)
            self.recv_status.config(
                text="✗ incomplete — read %d frame(s), missing indices %r" % (
                    payload["read"], payload["missing"]))
        elif kind == "error":
            where, msg = payload
            self._set_busy(self.send_bar, False)
            self._set_busy(self.recv_bar, False)
            messagebox.showerror("cimbar — %s error" % where, msg)

    # ---------------- preview animation ----------------
    def _stop_anim(self):
        if self._anim_job:
            self.root.after_cancel(self._anim_job)
            self._anim_job = None
        self.preview_imgs = []
        self.preview.config(image="")

    def _start_anim(self, frames):
        self._stop_anim()
        size = 360
        self.preview_imgs = [
            ImageTk.PhotoImage(f.resize((size, size), Image.LANCZOS)) for f in frames]
        self._anim_idx = 0
        self._tick_anim()

    def _tick_anim(self):
        if not self.preview_imgs:
            return
        self.preview.config(image=self.preview_imgs[self._anim_idx])
        self._anim_idx = (self._anim_idx + 1) % len(self.preview_imgs)
        delay = int(1000 / max(1, self.fps.get())) if len(self.preview_imgs) > 1 else 1000
        self._anim_job = self.root.after(delay, self._tick_anim)


def main():
    root = TkinterDnD.Tk() if _HAS_DND else tk.Tk()
    CimbarApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
