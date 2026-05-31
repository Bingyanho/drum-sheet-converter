import os
import subprocess
import sys
import threading
from pathlib import Path
from tkinter import BooleanVar, Canvas, DoubleVar, StringVar, Tk, filedialog, messagebox
from tkinter.scrolledtext import ScrolledText
from tkinter import ttk

from drum_auto import (
    DEFAULT_CONVERSION_MODE,
    DEFAULT_DELETE_DOWNLOADED_VIDEO,
    DEFAULT_INTERVAL,
    DEFAULT_SCROLL_INTERVAL,
    DEFAULT_SCROLL_MIN_CONTENT_DIFF,
    DEFAULT_SCROLL_MIN_SCORE,
    DEFAULT_THRESHOLD,
)


APP_DIR = Path(__file__).resolve().parent


class VideoSheetConverterGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Video Sheet Converter")
        self.root.geometry("1040x680")
        self.root.minsize(900, 620)
        self.process = None
        self.last_output_dir = None

        self.source = StringVar()
        self.name = StringVar()
        self.review = BooleanVar(value=False)
        self.report_json = BooleanVar(value=False)
        self.delete_downloaded_video = BooleanVar(value=DEFAULT_DELETE_DOWNLOADED_VIDEO)
        self.conversion_mode = StringVar(value=DEFAULT_CONVERSION_MODE)
        self.show_advanced = BooleanVar(value=False)
        self.rows_interval = DoubleVar(value=DEFAULT_INTERVAL)
        self.scroll_interval = DoubleVar(value=DEFAULT_SCROLL_INTERVAL)
        self.threshold = DoubleVar(value=DEFAULT_THRESHOLD)
        self.scroll_min_score = DoubleVar(value=DEFAULT_SCROLL_MIN_SCORE)
        self.scroll_min_content_diff = DoubleVar(value=DEFAULT_SCROLL_MIN_CONTENT_DIFF)
        self.roi_time = StringVar(value="")
        self.status = StringVar(value="Ready")
        self.output_hint = StringVar(value="No output yet")
        self.phase = StringVar(value="Idle")

        self.build_ui()

    def build_ui(self):
        self.configure_style()
        self.root.configure(bg="#eef2f6")

        shell = ttk.Frame(self.root, style="App.TFrame", padding=20)
        shell.pack(fill="both", expand=True)
        shell.columnconfigure(0, weight=0, minsize=360)
        shell.columnconfigure(1, weight=1)
        shell.rowconfigure(1, weight=1)

        self.build_header(shell)
        self.build_left_panel(shell)
        self.build_right_panel(shell)

    def configure_style(self):
        style = ttk.Style()
        preferred_theme = "vista" if "vista" in style.theme_names() else "clam"
        style.theme_use(preferred_theme)
        style.configure(".", font=("Segoe UI", 10))
        style.configure("App.TFrame", background="#eef2f6")
        style.configure("Surface.TFrame", background="#ffffff", relief="flat")
        style.configure("Section.TFrame", background="#ffffff")
        style.configure("Title.TLabel", background="#eef2f6", foreground="#15202b", font=("Segoe UI", 20, "bold"))
        style.configure("Subtitle.TLabel", background="#eef2f6", foreground="#657386", font=("Segoe UI", 10))
        style.configure("CardTitle.TLabel", background="#ffffff", foreground="#1d2733", font=("Segoe UI", 11, "bold"))
        style.configure("Body.TLabel", background="#ffffff", foreground="#384554")
        style.configure("Muted.TLabel", background="#ffffff", foreground="#6b7788", font=("Segoe UI", 9))
        style.configure("Status.TLabel", background="#e8f1ff", foreground="#2457a6", font=("Segoe UI", 10, "bold"), padding=(12, 5))
        style.configure("Success.TLabel", background="#e6f6ec", foreground="#247a42", font=("Segoe UI", 10, "bold"), padding=(12, 5))
        style.configure("Error.TLabel", background="#fdecec", foreground="#a33434", font=("Segoe UI", 10, "bold"), padding=(12, 5))
        style.configure("Primary.TButton", font=("Segoe UI", 11, "bold"), padding=(18, 10))
        style.configure("Secondary.TButton", padding=(14, 8))
        style.configure("TEntry", padding=(8, 6))
        style.configure("TCheckbutton", background="#ffffff", foreground="#384554", padding=(0, 2))
        style.map("TCheckbutton", background=[("active", "#ffffff")], foreground=[("active", "#1d2733")])

    def build_header(self, parent):
        header = ttk.Frame(parent, style="App.TFrame")
        header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 18))
        header.columnconfigure(0, weight=1)

        ttk.Label(header, text="Video Sheet Converter", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            header,
            text="Capture score or document pages from videos and export clean printable files.",
            style="Subtitle.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))
        self.status_label = ttk.Label(header, textvariable=self.status, style="Status.TLabel")
        self.status_label.grid(row=0, column=1, rowspan=2, sticky="e")

    def build_left_panel(self, parent):
        shell = ttk.Frame(parent, style="Surface.TFrame", padding=0)
        shell.grid(row=1, column=0, sticky="nsew", padx=(0, 16))
        shell.columnconfigure(0, weight=1)
        shell.rowconfigure(0, weight=1)

        canvas = Canvas(shell, bg="#ffffff", highlightthickness=0, borderwidth=0)
        scrollbar = ttk.Scrollbar(shell, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        panel = ttk.Frame(canvas, style="Surface.TFrame", padding=18)
        window_id = canvas.create_window((0, 0), window=panel, anchor="nw")
        panel.columnconfigure(0, weight=1)

        def sync_scroll_region(event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfigure(window_id, width=canvas.winfo_width())

        def sync_canvas_width(event):
            canvas.itemconfigure(window_id, width=event.width)

        panel.bind("<Configure>", sync_scroll_region)
        canvas.bind("<Configure>", sync_canvas_width)

        def on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        canvas.bind("<Enter>", lambda event: canvas.bind_all("<MouseWheel>", on_mousewheel))
        canvas.bind("<Leave>", lambda event: canvas.unbind_all("<MouseWheel>"))

        self.build_input_section(panel)
        self.build_output_section(panel)
        self.build_advanced_section(panel)
        self.build_action_section(panel)

    def build_input_section(self, parent):
        section = ttk.Frame(parent, style="Section.TFrame")
        section.grid(row=0, column=0, sticky="ew", pady=(0, 18))
        section.columnconfigure(0, weight=1)

        ttk.Label(section, text="1. Choose Input", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(section, text="Use a local video file or paste a YouTube URL.", style="Muted.TLabel").grid(
            row=1, column=0, sticky="w", pady=(3, 10)
        )

        ttk.Label(section, text="Video or URL", style="Body.TLabel").grid(row=2, column=0, sticky="w")
        source_row = ttk.Frame(section, style="Section.TFrame")
        source_row.grid(row=3, column=0, sticky="ew", pady=(5, 12))
        source_row.columnconfigure(0, weight=1)
        ttk.Entry(source_row, textvariable=self.source).grid(row=0, column=0, sticky="ew")
        ttk.Button(source_row, text="Browse", style="Secondary.TButton", command=self.browse_video).grid(
            row=0, column=1, padx=(8, 0)
        )

        ttk.Label(section, text="Output name", style="Body.TLabel").grid(row=4, column=0, sticky="w")
        ttk.Entry(section, textvariable=self.name).grid(row=5, column=0, sticky="ew", pady=(5, 0))

        ttk.Label(section, text="Conversion type", style="Body.TLabel").grid(row=6, column=0, sticky="w", pady=(12, 0))
        mode_box = ttk.Combobox(
            section,
            textvariable=self.conversion_mode,
            values=("rows", "scroll"),
            state="readonly",
        )
        mode_box.grid(row=7, column=0, sticky="ew", pady=(5, 0))
        mode_box.bind("<<ComboboxSelected>>", lambda event: self.refresh_advanced_fields())
        ttk.Label(
            section,
            text="Use scroll when the selected page area moves downward continuously.",
            style="Muted.TLabel",
        ).grid(row=8, column=0, sticky="w", pady=(4, 0))

    def build_output_section(self, parent):
        section = ttk.Frame(parent, style="Section.TFrame")
        section.grid(row=1, column=0, sticky="ew", pady=(0, 18))
        section.columnconfigure(0, weight=1)

        ttk.Label(section, text="2. Output Options", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(section, text="Review captured images before creating PDF", variable=self.review).grid(
            row=1, column=0, sticky="w", pady=(10, 4)
        )
        ttk.Checkbutton(section, text="Save report.json", variable=self.report_json).grid(row=2, column=0, sticky="w")
        ttk.Checkbutton(
            section,
            text="Delete downloaded video after conversion",
            variable=self.delete_downloaded_video,
        ).grid(row=3, column=0, sticky="w", pady=(4, 0))

    def build_advanced_section(self, parent):
        section = ttk.Frame(parent, style="Section.TFrame")
        section.grid(row=2, column=0, sticky="ew", pady=(0, 18))
        section.columnconfigure(0, weight=1)

        ttk.Checkbutton(
            section,
            text="Advanced settings",
            variable=self.show_advanced,
            command=self.toggle_advanced,
        ).grid(row=0, column=0, sticky="w")

        self.advanced_box = ttk.Frame(section, style="Section.TFrame")
        self.advanced_box.columnconfigure(1, weight=1)
        self.refresh_advanced_fields()

    def add_advanced_row(self, row, label, variable):
        ttk.Label(self.advanced_box, text=label, style="Body.TLabel").grid(row=row, column=0, sticky="w", pady=(10, 0))
        ttk.Entry(self.advanced_box, textvariable=variable, width=22).grid(row=row, column=1, sticky="ew", padx=(14, 0), pady=(10, 0))

    def refresh_advanced_fields(self):
        if not hasattr(self, "advanced_box"):
            return
        for child in self.advanced_box.winfo_children():
            child.destroy()

        self.advanced_box.columnconfigure(1, weight=1)
        self.add_advanced_row(0, "Crop preview time", self.roi_time)
        if self.conversion_mode.get() == "scroll":
            self.add_advanced_row(1, "Scroll interval", self.scroll_interval)
            self.add_advanced_row(2, "Scroll match score", self.scroll_min_score)
            self.add_advanced_row(3, "New content diff", self.scroll_min_content_diff)
            reset_row = 4
        else:
            self.add_advanced_row(1, "Rows interval", self.rows_interval)
            self.add_advanced_row(2, "Capture threshold", self.threshold)
            reset_row = 3

        actions = ttk.Frame(self.advanced_box, style="Section.TFrame")
        actions.grid(row=reset_row, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        ttk.Button(actions, text="Reset defaults", style="Secondary.TButton", command=self.reset_defaults).pack(side="left")

    def toggle_advanced(self):
        if self.show_advanced.get():
            self.advanced_box.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        else:
            self.advanced_box.grid_forget()

    def build_action_section(self, parent):
        section = ttk.Frame(parent, style="Section.TFrame")
        section.grid(row=3, column=0, sticky="sew")
        section.columnconfigure(0, weight=1)

        self.convert_button = ttk.Button(
            section,
            text="Select Area and Convert",
            style="Primary.TButton",
            command=self.start_convert,
        )
        self.convert_button.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        button_row = ttk.Frame(section, style="Section.TFrame")
        button_row.grid(row=1, column=0, sticky="ew")
        button_row.columnconfigure(0, weight=1)
        button_row.columnconfigure(1, weight=1)
        self.stop_button = ttk.Button(button_row, text="Stop", style="Secondary.TButton", command=self.stop_convert)
        self.stop_button.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.output_button = ttk.Button(
            button_row,
            text="Open Output",
            style="Secondary.TButton",
            command=self.open_output_folder,
            state="disabled",
        )
        self.output_button.grid(row=0, column=1, sticky="ew", padx=(6, 0))

    def build_right_panel(self, parent):
        panel = ttk.Frame(parent, style="Surface.TFrame", padding=18)
        panel.grid(row=1, column=1, sticky="nsew")
        panel.columnconfigure(0, weight=1)
        panel.rowconfigure(3, weight=1)

        ttk.Label(panel, text="Progress", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            panel,
            text="A crop-selection window will open after conversion starts.",
            style="Muted.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(3, 12))

        summary = ttk.Frame(panel, style="Section.TFrame")
        summary.grid(row=2, column=0, sticky="ew", pady=(0, 12))
        summary.columnconfigure(0, weight=1)
        ttk.Label(summary, textvariable=self.output_hint, style="Body.TLabel").grid(row=0, column=0, sticky="w")
        progress_row = ttk.Frame(summary, style="Section.TFrame")
        progress_row.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        progress_row.columnconfigure(1, weight=1)
        ttk.Label(progress_row, textvariable=self.phase, style="Muted.TLabel", width=13).grid(row=0, column=0, sticky="w", padx=(0, 10))
        self.progress = ttk.Progressbar(progress_row, mode="determinate", maximum=100)
        self.progress.grid(row=0, column=1, sticky="ew")

        self.log = ScrolledText(
            panel,
            height=18,
            wrap="word",
            font=("Cascadia Mono", 9),
            bg="#f8fafc",
            fg="#1f2937",
            insertbackground="#1f2937",
            relief="flat",
            padx=12,
            pady=10,
        )
        self.log.grid(row=3, column=0, sticky="nsew")

    def browse_video(self):
        path = filedialog.askopenfilename(
            title="Choose a video",
            filetypes=[
                ("Video files", "*.mp4 *.avi *.mov *.mkv *.webm"),
                ("All files", "*.*"),
            ],
        )
        if path:
            self.source.set(path)
            if not self.name.get():
                self.name.set(Path(path).stem)

    def reset_defaults(self):
        self.rows_interval.set(DEFAULT_INTERVAL)
        self.scroll_interval.set(DEFAULT_SCROLL_INTERVAL)
        self.threshold.set(DEFAULT_THRESHOLD)
        self.scroll_min_score.set(DEFAULT_SCROLL_MIN_SCORE)
        self.scroll_min_content_diff.set(DEFAULT_SCROLL_MIN_CONTENT_DIFF)
        self.roi_time.set("")

    def build_command(self):
        source = self.source.get().strip()
        if not source:
            raise ValueError("Please choose a video file or paste a YouTube URL.")

        if getattr(sys, "frozen", False):
            command = [sys.executable, "--cli", source]
        else:
            command = [sys.executable, str(APP_DIR / "drum_auto.py"), source]
        if self.name.get().strip():
            command.extend(["--name", self.name.get().strip()])
        command.extend(["--mode", self.conversion_mode.get()])
        command.extend(
            [
                "--interval",
                str(self.scroll_interval.get() if self.conversion_mode.get() == "scroll" else self.rows_interval.get()),
                "--threshold",
                str(self.threshold.get()),
                "--scroll-min-score",
                str(self.scroll_min_score.get()),
                "--scroll-min-content-diff",
                str(self.scroll_min_content_diff.get()),
            ]
        )
        if self.review.get() and self.conversion_mode.get() == "rows":
            command.append("--review")
        if self.report_json.get():
            command.append("--report-json")
        if not self.delete_downloaded_video.get():
            command.append("--keep-downloaded-video")
        roi_time = self.roi_time.get().strip()
        if roi_time:
            command.extend(["--roi-time", roi_time])
        return command

    def set_status(self, text, style="Status.TLabel"):
        self.status.set(text)
        self.status_label.configure(style=style)

    def start_convert(self):
        if self.process and self.process.poll() is None:
            messagebox.showinfo("Already running", "A conversion is already running.")
            return
        try:
            command = self.build_command()
        except Exception as exc:
            messagebox.showerror("Input needed", str(exc))
            return

        self.last_output_dir = None
        self.output_hint.set("Waiting for output folder...")
        self.phase.set("Preparing")
        self.progress.stop()
        self.progress.configure(mode="determinate", value=0)
        self.output_button.configure(state="disabled")
        self.convert_button.configure(state="disabled")
        self.set_status("Running", "Status.TLabel")
        self.log.delete("1.0", "end")
        self.append_log("> " + " ".join(f'"{part}"' if " " in part else part for part in command) + "\n\n")
        threading.Thread(target=self.run_command, args=(command,), daemon=True).start()

    def run_command(self, command):
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8:replace"
        env["PYTHONUNBUFFERED"] = "1"
        self.process = subprocess.Popen(
            command,
            cwd=str(APP_DIR),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        for line in self.process.stdout:
            self.root.after(0, self.handle_output_line, line)
        return_code = self.process.wait()
        self.root.after(0, self.finish_process, return_code)

    def handle_output_line(self, line):
        clean_line = line.strip()
        if clean_line.startswith("Output folder:"):
            self.last_output_dir = Path(line.split(":", 1)[1].strip())
            self.output_hint.set(f"Output: {self.last_output_dir}")
            self.output_button.configure(state="normal")
        elif clean_line.startswith("Detected YouTube/web URL"):
            self.phase.set("Downloading")
            self.progress.stop()
            self.progress.configure(mode="determinate", value=0)
        elif clean_line.startswith("Download progress:"):
            self.phase.set("Downloading")
            self.progress.stop()
            self.progress.configure(mode="determinate")
            self.update_progress_from_line(clean_line)
        elif clean_line.startswith("Preparing crop preview"):
            self.phase.set("Preview")
            self.progress.configure(mode="indeterminate")
            self.progress.start(12)
        elif clean_line.startswith("Preview search:"):
            self.phase.set("Preview")
            if str(self.progress.cget("mode")) != "indeterminate":
                self.progress.configure(mode="indeterminate")
                self.progress.start(12)
        elif clean_line.startswith("Analyzing video:"):
            self.progress.stop()
            self.phase.set("Converting")
            self.progress.configure(mode="determinate", value=0)
        elif clean_line.startswith("Convert progress:"):
            self.phase.set("Converting")
            self.update_progress_from_line(clean_line)
        self.append_log(line)

    def update_progress_from_line(self, line):
        try:
            value = int(line.rsplit(":", 1)[1].strip().rstrip("%"))
        except ValueError:
            return
        self.progress.configure(value=max(0, min(100, value)))

    def finish_process(self, return_code):
        self.append_log(f"\nProcess finished with code {return_code}\n")
        if return_code == 0:
            self.progress.stop()
            self.set_status("Done", "Success.TLabel")
            self.phase.set("Complete")
            self.progress.configure(mode="determinate", value=100)
        else:
            self.progress.stop()
            self.set_status("Failed", "Error.TLabel")
            self.phase.set("Stopped")
        self.convert_button.configure(state="normal")
        if self.last_output_dir:
            self.output_button.configure(state="normal")

    def append_log(self, text):
        self.log.insert("end", text)
        self.log.see("end")

    def stop_convert(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            self.append_log("\nStop requested.\n")
            self.set_status("Stopping", "Status.TLabel")
            self.phase.set("Stopping")
            self.progress.stop()

    def open_output_folder(self):
        if self.last_output_dir and self.last_output_dir.exists():
            os.startfile(self.last_output_dir)
        else:
            messagebox.showinfo("No output yet", "Run a conversion first.")


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--cli":
        from drum_auto import main as cli_main

        sys.argv = [sys.argv[0], *sys.argv[2:]]
        try:
            cli_main()
        except KeyboardInterrupt:
            print("\nCancelled.")
            sys.exit(130)
        except Exception as exc:
            print(f"\nError: {exc}")
            sys.exit(1)
        return

    root = Tk()
    VideoSheetConverterGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
