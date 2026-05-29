# Manual Drum Sheet Converter

Convert dynamic drum-sheet videos into printable JPG/PDF sheet pages.

The app starts with manual crop selection, then supports two conversion modes:

- `rows`: captures changed staff rows from dynamic row-based drum sheets.
- `scroll`: stitches vertically scrolling full-page scores into a long sheet, then splits it into printable A4 pages.

## Project Files

- `drum_gui.py`: user-friendly desktop GUI.
- `drum_auto.py`: command-line converter and core image-processing logic.
- `requirements.txt`: Python dependencies.
- `.gitignore`: excludes generated videos, sheet outputs, and cache files.

Generated folders such as `downloads/`, `sheet/`, and `pic/` are not required for distribution.

## Install

Use Python 3.10 or newer.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Run GUI

```powershell
python .\drum_gui.py
```

On Windows, users can also double-click:

```text
run_gui.bat
```

Basic workflow:

1. Choose a local video or paste a YouTube URL.
2. Enter an output name.
3. Select conversion type:
   - `rows` for row-changing dynamic sheets.
   - `scroll` for full-page scores that move downward.
4. Click `Select Area and Convert`.
5. Drag-select the drum-sheet area in the preview window.
6. Check the generated PDF in the output folder.

## Command Line

Rows mode:

```powershell
python .\drum_auto.py .\video.mp4 --name song_name --mode rows --review --report-json
```

Scroll mode:

```powershell
python .\drum_auto.py .\video.mp4 --name song_name --mode scroll --interval 0.35 --report-json
```

YouTube URL:

```powershell
python .\drum_auto.py "https://youtu.be/example" --name song_name --mode scroll
```

Downloaded YouTube videos are deleted after successful conversion by default.
Use `--keep-downloaded-video` if you want to keep them.

## Common Parameters

- `--interval`: seconds between scanned frames.
- `--review`: review captured rows before PDF generation. Rows mode only.
- `--report-json`: save processing statistics.
- `--delete-temp`: delete intermediate captured images.

Rows mode:

- `--threshold`: lower values keep smaller frame changes.
- `--duplicate-threshold`: lower values keep more similar-looking rows.

Scroll mode:

- `--scroll-max-shift`: maximum vertical movement to search per scan.
- `--scroll-min-shift`: minimum movement before appending new content.
- `--scroll-min-score`: maximum alignment error accepted for stitching.

## Sharing With Others

Recommended options:

1. Put the project on GitHub with only source files:
   - `drum_auto.py`
   - `drum_gui.py`
   - `requirements.txt`
   - `README.md`
   - `.gitignore`
   - `run_gui.bat`
2. Do not upload generated folders:
   - `downloads/`
   - `sheet/`
   - `pic/`
   - `__pycache__/`
3. Ask users to install dependencies with `pip install -r requirements.txt`.
4. For non-programmers, package the GUI as an `.exe` with PyInstaller:

```powershell
python -m pip install pyinstaller
pyinstaller --onefile --windowed --name DrumSheetConverter drum_gui.py
```

The executable will be created under `dist/`.
