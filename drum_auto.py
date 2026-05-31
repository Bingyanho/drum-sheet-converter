import argparse
import json
import math
import re
import shutil
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import cv2
import numpy as np


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

A4_WIDTH = 1240
A4_HEIGHT = 1754
WHITE = (255, 255, 255)

# Tunable defaults
DEFAULT_INTERVAL = 1.5
DEFAULT_THRESHOLD = 1.5
DEFAULT_DUPLICATE_THRESHOLD = 1.5
DEFAULT_ROI_MARGIN = 0.0
DEFAULT_PREVIEW_WIDTH = 960
DEFAULT_PREVIEW_HEIGHT = 540
DEFAULT_MAX_FRAMES = 0
DEFAULT_DELETE_DOWNLOADED_VIDEO = True
DEFAULT_CONVERSION_MODE = "rows"
DEFAULT_SCROLL_INTERVAL = 1.0
DEFAULT_SCROLL_MAX_SHIFT = 180
DEFAULT_SCROLL_MIN_SHIFT = 8
DEFAULT_SCROLL_MIN_SCORE = 18.0
SCROLL_PAGE_BREAK_SEARCH = 180
# Validation thresholds.
MIN_ROI_ASPECT = 2.5
MIN_WHITE_RATIO = 0.62
MIN_DARK_RATIO = 0.006
MAX_DARK_RATIO = 0.35
MIN_STAFF_ROWS = 4
MIN_HORIZONTAL_LINES = 3

def imread(path):
    data = np.fromfile(str(path), dtype=np.uint8)
    if data.size == 0:
        return None
    return cv2.imdecode(data, cv2.IMREAD_COLOR)


def imwrite(path, image):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    ext = path.suffix or ".jpg"
    ok, encoded = cv2.imencode(ext, image)
    if not ok:
        return False
    encoded.tofile(str(path))
    return True


def safe_name(text):
    text = re.sub(r'[\\/:*?"<>|]+', "_", text).strip()
    text = re.sub(r"\s+", "_", text)
    return text or "drum_sheet"


def make_unique_dir(path):
    path = Path(path)
    if not path.exists():
        path.mkdir(parents=True)
        return path

    for index in range(2, 1000):
        candidate = path.with_name(f"{path.name}_{index}")
        if not candidate.exists():
            candidate.mkdir(parents=True)
            return candidate
    raise RuntimeError(f"Cannot create output folder: {path}")


def is_url(source):
    parsed = urlparse(source)
    return parsed.scheme in {"http", "https"}


def download_youtube(source, download_dir, cookies_from_browser=None):
    try:
        from yt_dlp import YoutubeDL
    except ImportError as exc:
        raise RuntimeError(
            "Missing yt-dlp. Please run: python -m pip install -r requirements.txt"
        ) from exc

    download_dir.mkdir(parents=True, exist_ok=True)
    progress_state = {"last": -1}

    def progress_hook(status):
        if status.get("status") == "downloading":
            total = status.get("total_bytes") or status.get("total_bytes_estimate")
            downloaded = status.get("downloaded_bytes", 0)
            if total:
                percent = int(downloaded * 100 / total)
                if percent >= progress_state["last"] + 5:
                    progress_state["last"] = percent
                    print(f"Download progress: {percent}%", flush=True)
        elif status.get("status") == "finished":
            progress_state["last"] = 100
            print("Download progress: 100%", flush=True)

    options = {
        "format": "bv*[ext=mp4]/best[ext=mp4][vcodec!=none]/best",
        "outtmpl": str(download_dir / "%(id)s.%(ext)s"),
        "noplaylist": True,
        "quiet": False,
        "restrictfilenames": True,
        "progress_hooks": [progress_hook],
    }
    if cookies_from_browser:
        options["cookiesfrombrowser"] = (cookies_from_browser, None, None, None)
        print(f"Using cookies from browser: {cookies_from_browser}")

    with YoutubeDL(options) as ydl:
        try:
            info = ydl.extract_info(source, download=True)
        except Exception as exc:
            text = str(exc)
            if "Sign in to confirm" in text or "not a bot" in text:
                raise RuntimeError(
                    "YouTube blocked this download and asked for browser login cookies. "
                    "In the GUI, enable 'Use browser cookies for YouTube' and choose the browser "
                    "where you are logged into YouTube, then try again."
                ) from exc
            raise
        filename = ydl.prepare_filename(info)
        mp4_path = Path(filename).with_suffix(".mp4")
        return mp4_path if mp4_path.exists() else Path(filename)


def resolve_source(source, work_dir, cookies_from_browser=None):
    if is_url(source):
        print("Detected YouTube/web URL. Downloading video...")
        return download_youtube(source, work_dir / "downloads", cookies_from_browser)

    path = Path(source).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"Video file not found: {path}")
    return path


def prepare_video_for_opencv(video_path):
    video_path = Path(video_path)
    try:
        str(video_path).encode("ascii")
        return video_path, None
    except UnicodeEncodeError:
        temp_dir = Path(tempfile.gettempdir()) / "drum_auto"
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp_path = temp_dir / f"{safe_name(video_path.stem)}{video_path.suffix}"
        shutil.copy2(video_path, temp_path)
        return temp_path, temp_path


def frame_content_score(frame):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return float(np.mean(gray) + np.std(gray))


def read_roi_preview_frame(video_path, preferred_time):
    print("Preparing crop preview frame...", flush=True)
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise RuntimeError("OpenCV cannot open the video.")

    fps = capture.get(cv2.CAP_PROP_FPS) or 30
    frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    duration = frame_count / fps if frame_count else 0

    candidate_times = []
    if preferred_time is not None:
        candidate_times.append(max(0, float(preferred_time)))
    elif duration > 0:
        candidate_times.extend(
            [
                min(duration * 0.05, 10),
                min(duration * 0.10, 20),
                min(duration * 0.20, 40),
                min(duration * 0.35, 80),
                min(duration * 0.50, 120),
            ]
        )
    else:
        candidate_times.extend([3, 8, 15, 30, 60])

    best_frame = None
    best_time = 0.0
    best_score = -1.0
    seen_times = set()
    for seconds in candidate_times:
        seconds = round(float(seconds), 2)
        if seconds in seen_times:
            continue
        seen_times.add(seconds)
        print(f"Preview search: reading frame near {seconds:.1f}s", flush=True)
        capture.set(cv2.CAP_PROP_POS_MSEC, seconds * 1000)
        ok, frame = capture.read()
        if not ok:
            continue
        score = frame_content_score(frame)
        if score > best_score:
            best_frame = frame
            best_time = seconds
            best_score = score

    capture.release()
    if best_frame is None:
        raise RuntimeError("Cannot read a useful video frame for crop selection.")
    return best_frame, best_time, best_score


def resize_for_preview(frame, max_width=960, max_height=540):
    height, width = frame.shape[:2]
    scale = min(max_width / width, max_height / height, 1.0)
    if scale >= 1.0:
        return frame, 1.0
    resized = cv2.resize(
        frame,
        (int(width * scale), int(height * scale)),
        interpolation=cv2.INTER_AREA,
    )
    return resized, scale


def draw_window_header(canvas, title, subtitle):
    cv2.rectangle(canvas, (0, 0), (canvas.shape[1], 58), (32, 38, 46), -1)
    cv2.putText(canvas, title, (18, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.68, (245, 248, 252), 2, cv2.LINE_AA)
    cv2.putText(canvas, subtitle, (18, 48), cv2.FONT_HERSHEY_SIMPLEX, 0.46, (185, 195, 208), 1, cv2.LINE_AA)


def draw_framed_preview(image, title, subtitle, header_height=58, background=(24, 28, 34)):
    canvas = np.full(
        (image.shape[0] + header_height, image.shape[1], 3),
        background,
        dtype=np.uint8,
    )
    draw_window_header(canvas, title, subtitle)
    canvas[header_height : header_height + image.shape[0], 0 : image.shape[1]] = image
    return canvas


def select_roi_with_preview(preview):
    header_height = 58
    state = {
        "dragging": False,
        "start": None,
        "end": None,
        "confirmed": False,
        "cancelled": False,
    }

    def clamp_point(x, y):
        return (
            max(0, min(x, preview.shape[1] - 1)),
            max(0, min(y - header_height, preview.shape[0] - 1)),
        )

    def on_mouse(event, x, y, flags, param):
        if y < header_height:
            return
        point = clamp_point(x, y)
        if event == cv2.EVENT_LBUTTONDOWN:
            state["dragging"] = True
            state["start"] = point
            state["end"] = point
        elif event == cv2.EVENT_MOUSEMOVE and state["dragging"]:
            state["end"] = point
        elif event == cv2.EVENT_LBUTTONUP and state["dragging"]:
            state["dragging"] = False
            state["end"] = point

    window_name = "Select drum sheet area"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.setMouseCallback(window_name, on_mouse)

    while True:
        canvas = draw_framed_preview(
            preview,
            "Select Drum Sheet Area",
            "Drag over the sheet. Enter/Space: confirm  R: reset  Esc/C: cancel",
            header_height,
        )
        if state["start"] and state["end"]:
            x1, y1 = state["start"]
            x2, y2 = state["end"]
            left, right = sorted((x1, x2))
            top, bottom = sorted((y1, y2))
            overlay = canvas.copy()
            cv2.rectangle(
                overlay,
                (left, top + header_height),
                (right, bottom + header_height),
                (30, 150, 255),
                -1,
            )
            canvas = cv2.addWeighted(overlay, 0.18, canvas, 0.82, 0)
            cv2.rectangle(canvas, (left, top + header_height), (right, bottom + header_height), (0, 190, 255), 2)
            cv2.putText(
                canvas,
                f"{right - left} x {bottom - top}",
                (left + 8, max(header_height + 22, top + header_height - 8)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (0, 190, 255),
                2,
                cv2.LINE_AA,
            )

        cv2.imshow(window_name, canvas)
        key = cv2.waitKey(20) & 0xFF
        if key in {13, 32}:
            state["confirmed"] = True
            break
        if key in {27, ord("c"), ord("C")}:
            state["cancelled"] = True
            break
        if key in {ord("r"), ord("R")}:
            state["start"] = None
            state["end"] = None

    cv2.destroyWindow(window_name)
    if state["cancelled"] or not state["start"] or not state["end"]:
        return 0, 0, 0, 0

    x1, y1 = state["start"]
    x2, y2 = state["end"]
    left, right = sorted((x1, x2))
    top, bottom = sorted((y1, y2))
    return left, top, right - left, bottom - top


def select_manual_roi(video_path, roi_time, preview_width, preview_height, margin_ratio):
    frame, seconds, score = read_roi_preview_frame(video_path, roi_time)
    preview, scale = resize_for_preview(frame, preview_width, preview_height)
    print(f"Using a frame near {seconds:.1f}s for crop selection. score={score:.1f}")
    print("Drag-select the drum sheet area, then press Enter/Space. Press Esc/C to cancel.")

    selected = select_roi_with_preview(preview)

    x, y, w, h = [int(round(value / scale)) for value in selected]
    if w <= 0 or h <= 0:
        raise RuntimeError("No drum sheet area selected.")

    margin_x = int(round(w * margin_ratio))
    margin_y = int(round(h * margin_ratio))
    frame_h, frame_w = frame.shape[:2]
    x = max(0, x - margin_x)
    y = max(0, y - margin_y)
    right = min(frame_w, x + w + margin_x * 2)
    bottom = min(frame_h, y + h + margin_y * 2)
    return x, y, right - x, bottom - y


def crop_frame(frame, roi):
    x, y, w, h = roi
    return frame[y : y + h, x : x + w]


def white_paper_mask(frame):
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    return cv2.inRange(hsv, (0, 0, 175), (179, 85, 255))


def count_staff_like_rows(gray_roi):
    if gray_roi.size == 0:
        return 0
    h = gray_roi.shape[0]
    dark = gray_roi < 115
    row_dark_ratio = np.mean(dark, axis=1)
    long_dark_rows = row_dark_ratio > 0.08

    groups = 0
    in_group = False
    gap = 0
    min_gap = max(1, h // 150)
    for is_dark in long_dark_rows:
        if is_dark:
            if not in_group:
                groups += 1
                in_group = True
            gap = 0
        elif in_group:
            gap += 1
            if gap > min_gap:
                in_group = False
    return groups


def count_long_horizontal_lines(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    dark = cv2.inRange(gray, 0, 125)
    width = image.shape[1]
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(80, width // 4), 1))
    horizontal = cv2.morphologyEx(dark, cv2.MORPH_OPEN, kernel, iterations=1)
    contours, _ = cv2.findContours(horizontal, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    lines = 0
    for contour in contours:
        _, _, w, h = cv2.boundingRect(contour)
        if w >= width * 0.30 and h <= max(6, image.shape[0] * 0.08):
            lines += 1
    return lines


def validate_sheet_crop(crop):
    if crop.size == 0:
        return False, "empty"

    height, width = crop.shape[:2]
    if width < 300 or height < 40 or width / max(height, 1) < MIN_ROI_ASPECT:
        return False, "bad-shape"

    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    paper = white_paper_mask(crop)
    white_ratio = float(np.mean(paper > 0))
    dark_ratio = float(np.mean(gray < 130))
    staff_rows = count_staff_like_rows(gray)
    horizontal_lines = count_long_horizontal_lines(crop)

    if white_ratio < MIN_WHITE_RATIO:
        return False, f"low-white:{white_ratio:.2f}"
    if dark_ratio < MIN_DARK_RATIO or dark_ratio > MAX_DARK_RATIO:
        return False, f"bad-dark:{dark_ratio:.2f}"
    if staff_rows < MIN_STAFF_ROWS or horizontal_lines < MIN_HORIZONTAL_LINES:
        return False, f"few-lines:{staff_rows}/{horizontal_lines}"

    return True, (
        f"white={white_ratio:.2f}, dark={dark_ratio:.2f}, "
        f"lines={staff_rows}/{horizontal_lines}"
    )


def should_skip_failed_validation(reason):
    reason_type = reason.split(":", 1)[0]
    if reason_type in {"empty", "bad-shape"}:
        return True
    # Manual mode trusts the selected ROI, but still rejects frames whose
    # brightness/darkness profile is clearly not a drum sheet.
    return reason_type in {"low-white", "bad-dark"}


def frame_difference_score(previous, current):
    previous_gray = cv2.cvtColor(previous, cv2.COLOR_BGR2GRAY)
    current_gray = cv2.cvtColor(current, cv2.COLOR_BGR2GRAY)
    previous_small = cv2.resize(previous_gray, (320, 120), interpolation=cv2.INTER_AREA)
    current_small = cv2.resize(current_gray, (320, 120), interpolation=cv2.INTER_AREA)
    return float(np.mean(cv2.absdiff(previous_small, current_small)))


def canonicalize_for_fingerprint(gray):
    dark = gray < 180
    if not np.any(dark):
        return gray

    rows = np.where(np.mean(dark, axis=1) > 0.003)[0]
    cols = np.where(np.mean(dark, axis=0) > 0.003)[0]
    if rows.size == 0 or cols.size == 0:
        return gray

    top = int(rows[0])
    bottom = int(rows[-1]) + 1
    left = int(cols[0])
    right = int(cols[-1]) + 1

    height, width = gray.shape[:2]
    pad_y = max(12, int(round((bottom - top) * 0.12)))
    pad_x = max(20, int(round((right - left) * 0.02)))
    return gray[
        max(0, top - pad_y) : min(height, bottom + pad_y),
        max(0, left - pad_x) : min(width, right + pad_x),
    ]


def sheet_fingerprint(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray = canonicalize_for_fingerprint(gray)
    resized = cv2.resize(gray, (640, 160), interpolation=cv2.INTER_AREA)
    binary = cv2.adaptiveThreshold(
        resized,
        255,
        cv2.ADAPTIVE_THRESH_MEAN_C,
        cv2.THRESH_BINARY_INV,
        21,
        12,
    )
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel, iterations=1)

    staff_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (42, 1))
    staff_lines = cv2.morphologyEx(binary, cv2.MORPH_OPEN, staff_kernel, iterations=1)
    content = cv2.subtract(binary, staff_lines)
    content = cv2.morphologyEx(content, cv2.MORPH_OPEN, kernel, iterations=1)
    return {
        "full": binary > 0,
        "content": content > 0,
        "content_density": float(np.mean(content > 0)),
    }


def shifted_binary_difference(previous, current, max_shift):
    best = 100.0
    for dy in range(-max_shift, max_shift + 1):
        for dx in range(-max_shift, max_shift + 1):
            if dy >= 0:
                prev_y = slice(dy, previous.shape[0])
                curr_y = slice(0, current.shape[0] - dy)
            else:
                prev_y = slice(0, previous.shape[0] + dy)
                curr_y = slice(-dy, current.shape[0])

            if dx >= 0:
                prev_x = slice(dx, previous.shape[1])
                curr_x = slice(0, current.shape[1] - dx)
            else:
                prev_x = slice(0, previous.shape[1] + dx)
                curr_x = slice(-dx, current.shape[1])

            previous_part = previous[prev_y, prev_x]
            current_part = current[curr_y, curr_x]
            if previous_part.size == 0 or current_part.size == 0:
                continue
            score = float(np.mean(previous_part != current_part) * 100.0)
            best = min(best, score)
    return best


def sheet_difference_score(previous_fingerprint, current_fingerprint):
    full_score = shifted_binary_difference(previous_fingerprint["full"], current_fingerprint["full"], 4)
    content_score = shifted_binary_difference(previous_fingerprint["content"], current_fingerprint["content"], 12)
    return min(full_score, content_score)


def effective_duplicate_threshold(fingerprint, duplicate_threshold):
    density = fingerprint["content_density"]
    if density < 0.020:
        return 0.0
    if density < 0.025:
        return duplicate_threshold * 0.35
    return duplicate_threshold


def extract_unique_frames(
    video_path,
    roi,
    output_dir,
    interval,
    threshold,
    duplicate_threshold,
    max_frames,
):
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise RuntimeError(f"OpenCV cannot open video: {video_path}")

    fps = capture.get(cv2.CAP_PROP_FPS) or 30
    frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    duration = frame_count / fps if frame_count else 0
    step = max(1, int(round(fps * interval)))
    total_scans = math.ceil(frame_count / step) if frame_count else 0

    output_dir.mkdir(parents=True, exist_ok=True)
    kept = []
    fingerprints = []
    previous_crop = None
    scanned = 0
    skipped_invalid = 0
    soft_invalid = 0
    invalid_reasons = {}
    skipped_low_change = 0
    skipped_duplicate = 0
    frame_index = 0
    last_progress = -1

    print(f"Analyzing video: fps={fps:.2f}, duration~{duration:.1f}s, scan every {interval:.2f}s")
    while True:
        ok, frame = capture.read()
        if not ok:
            break

        if frame_index % step != 0:
            frame_index += 1
            continue

        scanned += 1
        if total_scans:
            progress = min(99, int(scanned * 100 / total_scans))
            if progress >= last_progress + 5:
                last_progress = progress
                print(f"Convert progress: {progress}%", flush=True)

        crop = crop_frame(frame, roi)
        is_valid, validation_text = validate_sheet_crop(crop)
        if not is_valid:
            invalid_reasons[validation_text] = invalid_reasons.get(validation_text, 0) + 1
            if should_skip_failed_validation(validation_text):
                skipped_invalid += 1
                frame_index += 1
                continue
            soft_invalid += 1
            validation_text = f"warning:{validation_text}"

        fingerprint = sheet_fingerprint(crop)
        diff_score = 0.0
        duplicate_score = 100.0
        duplicate_limit = effective_duplicate_threshold(fingerprint, duplicate_threshold)
        should_keep = True

        if previous_crop is not None:
            diff_score = frame_difference_score(previous_crop, crop)
            duplicate_score = min(sheet_difference_score(old, fingerprint) for old in fingerprints[-1:])
            if diff_score < threshold:
                should_keep = False
                skipped_low_change += 1
            elif duplicate_score < duplicate_limit:
                should_keep = False
                skipped_duplicate += 1

        if should_keep:
            filename = output_dir / f"{len(kept) + 1:04d}.jpg"
            imwrite(filename, crop)
            kept.append(filename)
            fingerprints.append(fingerprint)
            previous_crop = crop.copy()
            print(
                f"keep {len(kept):03d}: {frame_index / fps:.1f}s, "
                f"diff={diff_score:.2f}, dup={duplicate_score:.2f}/{duplicate_limit:.2f}, "
                f"density={fingerprint['content_density']:.3f}, {validation_text}"
            )
            if max_frames and len(kept) >= max_frames:
                print(f"Reached --max-frames={max_frames}. Stop.")
                break

        frame_index += 1

    capture.release()
    print("Convert progress: 100%", flush=True)
    if not kept:
        raise RuntimeError("No frames were captured. Try lowering --threshold or selecting the ROI again.")

    stats = {
        "fps": fps,
        "duration_seconds": duration,
        "scan_interval_seconds": interval,
        "scanned_frames": scanned,
        "kept_frames": len(kept),
        "skipped_invalid_sheet": skipped_invalid,
        "soft_invalid_sheet": soft_invalid,
        "invalid_reasons": invalid_reasons,
        "skipped_low_change": skipped_low_change,
        "skipped_duplicates": skipped_duplicate,
    }
    print(f"Scanned {scanned} frames; kept {len(kept)}.")
    return kept, stats


def final_filter_sheet_images(image_paths, duplicate_threshold):
    filtered = []
    fingerprints = []
    skipped_duplicate = 0

    print("Running final duplicate filter...")
    for image_path in image_paths:
        image = imread(image_path)
        if image is None:
            print(f"final skip {image_path.name}: cannot read")
            continue

        fingerprint = sheet_fingerprint(image)
        duplicate_limit = effective_duplicate_threshold(fingerprint, duplicate_threshold)
        if fingerprints:
            duplicate_score = min(sheet_difference_score(old, fingerprint) for old in fingerprints[-1:])
            if duplicate_score < duplicate_limit:
                skipped_duplicate += 1
                print(f"final skip {image_path.name}: duplicate={duplicate_score:.2f}/{duplicate_limit:.2f}")
                continue

        filtered.append(image_path)
        fingerprints.append(fingerprint)

    if not filtered:
        raise RuntimeError("Final filter removed every image. Try lowering --duplicate-threshold.")

    stats = {
        "input_images": len(image_paths),
        "kept_images": len(filtered),
        "skipped_duplicates": skipped_duplicate,
    }
    print(f"Final filter kept {len(filtered)}/{len(image_paths)} images.")
    return filtered, stats


def estimate_vertical_scroll(previous, current, max_shift):
    previous_gray = cv2.cvtColor(previous, cv2.COLOR_BGR2GRAY)
    current_gray = cv2.cvtColor(current, cv2.COLOR_BGR2GRAY)
    height = min(previous_gray.shape[0], current_gray.shape[0])
    max_shift = min(max_shift, height - 20)
    if max_shift <= 0:
        return 0, 999.0

    previous_gray = previous_gray[:height, :]
    current_gray = current_gray[:height, :]
    best_shift = 0
    best_score = 999.0

    for shift in range(1, max_shift + 1):
        overlap_prev = previous_gray[shift:, :]
        overlap_curr = current_gray[: height - shift, :]
        if overlap_prev.size == 0:
            continue
        score = float(np.mean(cv2.absdiff(overlap_prev, overlap_curr)))
        if score < best_score:
            best_score = score
            best_shift = shift

    return best_shift, best_score


def find_scroll_page_break(resized, target_y, min_y, max_y):
    gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
    dark = gray < 170
    row_dark = np.mean(dark, axis=1)
    height = gray.shape[0]
    min_y = max(40, min_y)
    max_y = min(height - 40, max_y)
    if min_y >= max_y:
        return min(max(target_y, 0), height)

    best_y = target_y
    best_score = float("inf")
    for y in range(min_y, max_y + 1):
        top = max(0, y - 24)
        bottom = min(height, y + 24)
        band_score = float(np.mean(row_dark[top:bottom]))
        distance_penalty = abs(y - target_y) / max(1, SCROLL_PAGE_BREAK_SEARCH) * 0.025
        score = band_score + distance_penalty
        if score < best_score:
            best_score = score
            best_y = y
    return best_y


def make_scroll_pages(stitched_image, output_dir, base_name):
    height, width = stitched_image.shape[:2]
    resized_h = int(height * (A4_WIDTH / width))
    resized = cv2.resize(stitched_image, (A4_WIDTH, resized_h), interpolation=cv2.INTER_AREA)
    pages = []
    start = 0
    page_index = 0

    while start < resized_h:
        page = np.full((A4_HEIGHT, A4_WIDTH, 3), WHITE, dtype=np.uint8)
        if resized_h - start <= A4_HEIGHT:
            end = resized_h
        else:
            target = start + A4_HEIGHT
            end = find_scroll_page_break(
                resized,
                target,
                target - SCROLL_PAGE_BREAK_SEARCH,
                target,
            )
            if end <= start + A4_HEIGHT * 0.55:
                end = min(start + A4_HEIGHT, resized_h)
        end = min(end, start + A4_HEIGHT, resized_h)

        slice_img = resized[start:end, :]
        page[: slice_img.shape[0], :] = slice_img
        page_index += 1
        page_path = output_dir / f"{base_name}_{page_index:03d}.jpg"
        imwrite(page_path, page)
        pages.append(page_path)
        start = end
    return pages


def extract_scrolling_sheet(
    video_path,
    roi,
    output_dir,
    interval,
    max_shift,
    min_shift,
    min_score,
    max_frames,
):
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise RuntimeError(f"OpenCV cannot open video: {video_path}")

    fps = capture.get(cv2.CAP_PROP_FPS) or 30
    frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    duration = frame_count / fps if frame_count else 0
    step = max(1, int(round(fps * interval)))
    total_scans = math.ceil(frame_count / step) if frame_count else 0
    output_dir.mkdir(parents=True, exist_ok=True)

    previous_crop = None
    pieces = []
    scanned = 0
    accepted_shifts = 0
    skipped_small_shift = 0
    skipped_bad_match = 0
    total_shift = 0
    frame_index = 0
    last_progress = -1

    print(f"Analyzing scrolling sheet: fps={fps:.2f}, duration~{duration:.1f}s, scan every {interval:.2f}s")
    while True:
        ok, frame = capture.read()
        if not ok:
            break

        if frame_index % step != 0:
            frame_index += 1
            continue

        scanned += 1
        if total_scans:
            progress = min(99, int(scanned * 100 / total_scans))
            if progress >= last_progress + 5:
                last_progress = progress
                print(f"Convert progress: {progress}%", flush=True)

        crop = crop_frame(frame, roi)
        if crop.size == 0:
            frame_index += 1
            continue

        if previous_crop is None:
            pieces.append(crop.copy())
            previous_crop = crop.copy()
            frame_index += 1
            continue

        shift, score = estimate_vertical_scroll(previous_crop, crop, max_shift)
        if shift < min_shift:
            skipped_small_shift += 1
        elif score > min_score:
            skipped_bad_match += 1
        else:
            pieces.append(crop[-shift:, :].copy())
            total_shift += shift
            accepted_shifts += 1
            previous_crop = crop.copy()
            print(f"scroll keep {accepted_shifts:03d}: {frame_index / fps:.1f}s, shift={shift}, score={score:.2f}")
            if max_frames and accepted_shifts >= max_frames:
                print(f"Reached --max-frames={max_frames}. Stop.")
                break

        frame_index += 1

    capture.release()
    print("Convert progress: 100%", flush=True)
    if not pieces:
        raise RuntimeError("No scrolling sheet content was captured.")

    stitched = np.vstack(pieces)
    stitched_path = output_dir / "stitched_long_sheet.jpg"
    imwrite(stitched_path, stitched)
    stats = {
        "fps": fps,
        "duration_seconds": duration,
        "scan_interval_seconds": interval,
        "scanned_frames": scanned,
        "accepted_shifts": accepted_shifts,
        "total_scroll_pixels": total_shift,
        "stitched_height": int(stitched.shape[0]),
        "skipped_small_shift": skipped_small_shift,
        "skipped_bad_match": skipped_bad_match,
        "stitched_path": str(stitched_path),
    }
    print(f"Stitched scrolling sheet height={stitched.shape[0]}px, accepted shifts={accepted_shifts}.")
    return stitched, stitched_path, stats


def review_image_paths(image_paths, max_width=1100, max_height=760):
    kept = []
    removed = 0
    print("Review mode: press D/Delete/Backspace to remove, any other key to keep, Esc to stop.")

    for index, image_path in enumerate(image_paths, start=1):
        image = imread(image_path)
        if image is None:
            removed += 1
            continue

        preview, _ = resize_for_preview(image, max_width, max_height - 58)
        canvas = draw_framed_preview(
            preview,
            f"Review Captured Row {index}/{len(image_paths)}",
            "Enter/Space/K: keep  D/Delete/Backspace: remove  Esc: keep the rest",
        )
        cv2.rectangle(canvas, (0, 58), (canvas.shape[1] - 1, canvas.shape[0] - 1), (72, 82, 96), 1)
        cv2.putText(
            canvas,
            image_path.name,
            (18, canvas.shape[0] - 18),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.52,
            (80, 90, 105),
            1,
            cv2.LINE_AA,
        )
        cv2.imshow("Review captured drum sheets", canvas)
        key = cv2.waitKey(0) & 0xFF
        if key == 27:
            kept.extend(image_paths[index - 1 :])
            break
        if key in {8, 100, 127, ord("D")}:
            removed += 1
            print(f"review remove: {image_path.name}")
            continue
        kept.append(image_path)

    cv2.destroyAllWindows()
    if not kept:
        raise RuntimeError("Review removed every image.")
    print(f"Review kept {len(kept)}/{len(image_paths)} images.")
    return kept, {"reviewed": len(image_paths), "removed": removed}


def make_sheet_pages(image_paths, output_dir, base_name):
    first = imread(image_paths[0])
    if first is None:
        raise RuntimeError(f"Cannot read image: {image_paths[0]}")

    crop_h, crop_w = first.shape[:2]
    resized_h = int(crop_h * (A4_WIDTH / crop_w))
    if resized_h <= 0 or resized_h > A4_HEIGHT:
        raise RuntimeError("Selected drum sheet area is too tall for one A4 row.")

    rows_per_page = max(1, A4_HEIGHT // resized_h)
    page_count = math.ceil(len(image_paths) / rows_per_page)
    pages = []

    for page_index in range(page_count):
        page = np.full((A4_HEIGHT, A4_WIDTH, 3), WHITE, dtype=np.uint8)
        start = page_index * rows_per_page
        end = min(start + rows_per_page, len(image_paths))
        for row, image_path in enumerate(image_paths[start:end]):
            image = imread(image_path)
            if image is None:
                raise RuntimeError(f"Cannot read image: {image_path}")
            image = cv2.resize(image, (A4_WIDTH, resized_h), interpolation=cv2.INTER_AREA)
            top = row * resized_h
            page[top : top + resized_h, :] = image

        page_path = output_dir / f"{base_name}_{page_index + 1:03d}.jpg"
        imwrite(page_path, page)
        pages.append(page_path)
    return pages


def write_pdf(page_paths, pdf_path):
    try:
        from PIL import Image
    except ImportError:
        print("Missing Pillow. Skipping PDF. Please run: python -m pip install -r requirements.txt")
        return None

    images = [Image.open(path).convert("RGB") for path in page_paths]
    first, rest = images[0], images[1:]
    first.save(pdf_path, save_all=True, append_images=rest)
    for image in images:
        image.close()
    return pdf_path


def write_report(report_path, data):
    report_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return report_path


def build_parser():
    parser = argparse.ArgumentParser(
        description="Manually crop a dynamic drum sheet video and convert it into printable pages."
    )
    parser.add_argument("source", help="Local video path or YouTube URL")
    parser.add_argument("-n", "--name", help="Output sheet name. Defaults to the video file name.")
    parser.add_argument(
        "--mode",
        choices=["rows", "scroll"],
        default=DEFAULT_CONVERSION_MODE,
        help=f"rows captures changed staff rows; scroll stitches a vertically scrolling full sheet. Default: {DEFAULT_CONVERSION_MODE}",
    )
    parser.add_argument("--roi-time", type=float, help="Second used for manual crop selection.")
    parser.add_argument("--roi-margin", type=float, default=DEFAULT_ROI_MARGIN, help=f"Extra margin around selected crop. Default: {DEFAULT_ROI_MARGIN}")
    parser.add_argument("--preview-width", type=int, default=DEFAULT_PREVIEW_WIDTH, help=f"Crop selector max width. Default: {DEFAULT_PREVIEW_WIDTH}")
    parser.add_argument("--preview-height", type=int, default=DEFAULT_PREVIEW_HEIGHT, help=f"Crop selector max height. Default: {DEFAULT_PREVIEW_HEIGHT}")
    parser.add_argument("--interval", type=float, default=DEFAULT_INTERVAL, help=f"Scan interval in seconds. Default: {DEFAULT_INTERVAL}")
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD, help=f"Frame difference threshold. Default: {DEFAULT_THRESHOLD}")
    parser.add_argument("--duplicate-threshold", type=float, default=DEFAULT_DUPLICATE_THRESHOLD, help=f"Duplicate content threshold. Default: {DEFAULT_DUPLICATE_THRESHOLD}")
    parser.add_argument("--scroll-max-shift", type=int, default=DEFAULT_SCROLL_MAX_SHIFT, help=f"Maximum vertical scroll pixels per scan. Default: {DEFAULT_SCROLL_MAX_SHIFT}")
    parser.add_argument("--scroll-min-shift", type=int, default=DEFAULT_SCROLL_MIN_SHIFT, help=f"Minimum vertical scroll pixels needed to append content. Default: {DEFAULT_SCROLL_MIN_SHIFT}")
    parser.add_argument("--scroll-min-score", type=float, default=DEFAULT_SCROLL_MIN_SCORE, help=f"Maximum alignment difference allowed for scroll stitching. Default: {DEFAULT_SCROLL_MIN_SCORE}")
    parser.add_argument("--max-frames", type=int, default=DEFAULT_MAX_FRAMES, help=f"Maximum kept frames. {DEFAULT_MAX_FRAMES} means unlimited.")
    parser.add_argument("--review", action="store_true", help="Review captured rows before page generation.")
    parser.add_argument("--report-json", action="store_true", help="Write processing statistics to report.json.")
    parser.add_argument("--delete-temp", action="store_true", help="Delete temporary captured row images after output.")
    parser.add_argument(
        "--cookies-from-browser",
        choices=["chrome", "edge", "firefox", "brave", "opera", "vivaldi", "safari"],
        help="Use browser cookies for YouTube downloads that require sign-in.",
    )
    parser.add_argument(
        "--keep-downloaded-video",
        action="store_true",
        help="Keep YouTube/web video files after successful conversion. By default downloaded videos are deleted.",
    )
    return parser


def main():
    args = build_parser().parse_args()
    if getattr(sys, "frozen", False):
        work_dir = Path(sys.executable).resolve().parent
    else:
        work_dir = Path(__file__).resolve().parent
    source_is_url = is_url(args.source)
    video_path = resolve_source(args.source, work_dir, args.cookies_from_browser)
    opencv_video_path, temp_video_path = prepare_video_for_opencv(video_path)
    base_name = safe_name(args.name or video_path.stem)
    output_dir = make_unique_dir(work_dir / "sheet" / f"{base_name}")
    temp_dir = output_dir / ("scroll_parts" if args.mode == "scroll" else "captured_rows")

    print(f"Video source: {video_path}")
    if temp_video_path:
        print(f"OpenCV temp video: {temp_video_path}")
    print(f"Output folder: {output_dir}")

    roi = select_manual_roi(
        opencv_video_path,
        args.roi_time,
        args.preview_width,
        args.preview_height,
        args.roi_margin,
    )
    print(f"Selected crop: {roi}")

    filter_stats = {"input_images": 0, "kept_images": 0, "skipped_duplicates": 0}
    review_stats = {"reviewed": 0, "removed": 0}
    image_paths = []
    stitched_path = None

    if args.mode == "scroll":
        stitched_image, stitched_path, extraction_stats = extract_scrolling_sheet(
            opencv_video_path,
            roi,
            temp_dir,
            args.interval,
            args.scroll_max_shift,
            args.scroll_min_shift,
            args.scroll_min_score,
            args.max_frames,
        )
        page_paths = make_scroll_pages(stitched_image, output_dir, base_name)
    else:
        image_paths, extraction_stats = extract_unique_frames(
            opencv_video_path,
            roi,
            temp_dir,
            args.interval,
            args.threshold,
            args.duplicate_threshold,
            args.max_frames,
        )
        image_paths, filter_stats = final_filter_sheet_images(image_paths, args.duplicate_threshold)
        if args.review:
            image_paths, review_stats = review_image_paths(image_paths)
        page_paths = make_sheet_pages(image_paths, output_dir, base_name)

    pdf_path = write_pdf(page_paths, output_dir / f"{base_name}.pdf")

    report = {
        "source": str(video_path),
        "output_folder": str(output_dir),
        "base_name": base_name,
        "mode": args.mode,
        "roi": roi,
        "threshold": args.threshold,
        "duplicate_threshold": args.duplicate_threshold,
        "extraction": extraction_stats,
        "final_filter": filter_stats,
        "review": review_stats,
        "final_images": len(image_paths),
        "stitched_path": str(stitched_path) if stitched_path else None,
        "pages": len(page_paths),
        "page_paths": [str(path) for path in page_paths],
        "pdf_path": str(pdf_path) if pdf_path else None,
    }
    if args.report_json:
        report_path = write_report(output_dir / "report.json", report)
        print(f"- {report_path}")

    if args.delete_temp:
        shutil.rmtree(temp_dir, ignore_errors=True)
    if temp_video_path:
        temp_video_path.unlink(missing_ok=True)
    if source_is_url and DEFAULT_DELETE_DOWNLOADED_VIDEO and not args.keep_downloaded_video:
        try:
            video_path.unlink(missing_ok=True)
            print(f"Deleted downloaded video: {video_path}")
        except OSError as exc:
            print(f"Warning: could not delete downloaded video {video_path}: {exc}")

    print()
    if args.mode == "scroll":
        print(f"Done: stitched scrolling sheet, wrote {len(page_paths)} JPG page(s).")
        print(
            "Stats: "
            f"scanned={extraction_stats['scanned_frames']}, "
            f"accepted_shifts={extraction_stats['accepted_shifts']}, "
            f"height={extraction_stats['stitched_height']}, "
            f"bad_match={extraction_stats['skipped_bad_match']}"
        )
    else:
        print(f"Done: kept {len(image_paths)} sheet rows, wrote {len(page_paths)} JPG page(s).")
        print(
            "Stats: "
            f"scanned={extraction_stats['scanned_frames']}, "
            f"invalid={extraction_stats['skipped_invalid_sheet']}, "
            f"soft_invalid={extraction_stats['soft_invalid_sheet']}, "
            f"low_change={extraction_stats['skipped_low_change']}, "
            f"duplicates={extraction_stats['skipped_duplicates'] + filter_stats['skipped_duplicates']}, "
            f"review_removed={review_stats['removed']}"
        )
    for page_path in page_paths:
        print(f"- {page_path}")
    if pdf_path:
        print(f"- {pdf_path}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nCancelled.")
        sys.exit(130)
    except Exception as exc:
        print(f"\nError: {exc}")
        sys.exit(1)
