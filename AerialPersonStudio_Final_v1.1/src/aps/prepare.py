from __future__ import annotations
import csv
import hashlib
import math
import shutil
import zipfile
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from .config import PrepareConfig
from .dataset import StudioDataset, IMAGE_EXTS
from .paths import WorkspacePaths

VIDEO_EXTS = {".mp4", ".avi", ".mov", ".mkv", ".m4v", ".webm"}


def _safe_name(text: str) -> str:
    cleaned = "".join(c if c.isalnum() or c in "-_" else "_" for c in text.strip())
    return cleaned or "source"


def _phash(path: Path) -> int:
    img = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise ValueError(f"Unreadable image: {path}")
    img = cv2.resize(img, (32, 32), interpolation=cv2.INTER_AREA).astype(np.float32)
    dct = cv2.dct(img)
    block = dct[:8, :8]
    vals = block.flatten()[1:]
    med = float(np.median(vals))
    bits = (vals > med).astype(np.uint8)
    value = 0
    for b in bits:
        value = (value << 1) | int(b)
    return value


def _hamming(a: int, b: int) -> int:
    return int((a ^ b).bit_count())


def _quality(path: Path, cfg: PrepareConfig):
    img = cv2.imread(str(path))
    if img is None:
        return False, "unreadable", {}
    h, w = img.shape[:2]
    if w < cfg.min_width or h < cfg.min_height:
        return False, "too_small", {"width": w, "height": h}
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    mean = float(gray.mean())
    std = float(gray.std())
    blur = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    if cfg.black_filter_enabled and mean <= cfg.black_mean_threshold and std <= cfg.black_std_threshold:
        return False, "black_frame", {"width": w, "height": h, "mean": mean, "std": std, "blur": blur}
    if cfg.blur_filter_enabled and blur < cfg.blur_threshold:
        return False, "blur", {"width": w, "height": h, "mean": mean, "std": std, "blur": blur}
    return True, "ok", {"width": w, "height": h, "mean": mean, "std": std, "blur": blur}


def _allocate_source_groups(rows, cfg: PrepareConfig):
    """Approximate target image ratios while keeping each source entirely in one split.

    A bounded beam search is used instead of frame-level random splitting. This
    avoids leakage and gives much better split ratios than a naive greedy pass.
    """
    by_source = defaultdict(list)
    for r in rows:
        by_source[r["source_id"]].append(r)
    groups = sorted(by_source.items(), key=lambda kv: len(kv[1]), reverse=True)
    total = len(rows)
    targets = {
        "train": total * cfg.train_ratio,
        "val": total * cfg.val_ratio,
        "test": total * cfg.test_ratio,
    }
    split_names = ("train", "val", "test")

    # state: (train_count, val_count, test_count) -> assignments list
    states = {(0, 0, 0): []}
    beam = 6000
    for source, group in groups:
        g = len(group)
        nxt = {}
        for counts, assignments in states.items():
            for si, split in enumerate(split_names):
                c = list(counts); c[si] += g; key = tuple(c)
                candidate = assignments + [(source, split)]
                if key not in nxt:
                    nxt[key] = candidate
        def partial_score(item):
            counts = item[0]
            # normalized squared error; future groups can still improve it, so
            # this is only used to keep the search bounded.
            return sum(((counts[i] - targets[split_names[i]]) / max(1.0, targets[split_names[i]])) ** 2 for i in range(3))
        if len(nxt) > beam:
            best = sorted(nxt.items(), key=partial_score)[:beam]
            states = dict(best)
        else:
            states = nxt

    def final_score(item):
        counts, assignments = item
        score = sum(((counts[i] - targets[split_names[i]]) / max(1.0, targets[split_names[i]])) ** 2 for i in range(3))
        if len(groups) >= 3:
            # Strongly discourage an empty validation or test split when there
            # are enough independent sources to populate all three.
            if counts[1] == 0: score += 25
            if counts[2] == 0: score += 25
        return score

    best_counts, best_assignments = min(states.items(), key=final_score)
    source_to_split = dict(best_assignments)
    assigned = {k: [] for k in split_names}
    for source, group in groups:
        assigned[source_to_split[source]].extend(group)
    return assigned


def prepare_workspace(workspace: Path, cfg: PrepareConfig, progress=None, log=None):
    paths = WorkspacePaths(Path(workspace).resolve())
    paths.ensure()

    def say(msg):
        if log:
            log(msg)

    if paths.candidates.exists():
        shutil.rmtree(paths.candidates)
    paths.candidates.mkdir(parents=True, exist_ok=True)

    candidates = []
    # Still images
    stills = [p for p in paths.raw_images.rglob("*") if p.is_file() and p.suffix.lower() in IMAGE_EXTS]
    for i, src in enumerate(stills, start=1):
        rel_parent = src.parent.relative_to(paths.raw_images)
        source_id = _safe_name(str(rel_parent)) if str(rel_parent) != "." else _safe_name(src.stem)
        dst = paths.candidates / f"img_{i:06d}_{src.name}"
        shutil.copy2(src, dst)
        candidates.append({"path": dst, "source_id": source_id, "source_type": "image", "original_path": str(src), "timestamp_seconds": ""})
        if progress:
            progress("images", i, max(1, len(stills)), src.name)

    # Video extraction
    videos = [p for p in paths.raw_videos.rglob("*") if p.is_file() and p.suffix.lower() in VIDEO_EXTS]
    for vi, video in enumerate(videos, start=1):
        cap = cv2.VideoCapture(str(video))
        if not cap.isOpened():
            say(f"Skipped unreadable video: {video.name}")
            continue
        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        step = max(1, int(round(fps * cfg.video_frame_interval_seconds)))
        frame_idx = 0
        saved = 0
        source_id = _safe_name(video.stem)
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if frame_idx % step == 0:
                saved += 1
                dst = paths.candidates / f"vid_{vi:03d}_{saved:06d}.jpg"
                cv2.imwrite(str(dst), frame, [int(cv2.IMWRITE_JPEG_QUALITY), cfg.jpeg_quality])
                candidates.append({
                    "path": dst, "source_id": source_id, "source_type": "video",
                    "original_path": str(video), "timestamp_seconds": frame_idx / fps,
                })
            frame_idx += 1
            if progress and total_frames:
                progress("video", min(frame_idx, total_frames), total_frames, video.name)
        cap.release()
        say(f"Extracted {saved} frames from {video.name}")

    say(f"Candidates: {len(candidates)}")
    kept, rejected = [], []
    seen_hashes: list[int] = []
    for idx, item in enumerate(candidates, start=1):
        ok, reason, q = _quality(item["path"], cfg)
        if not ok:
            rejected.append({**item, **q, "reason": reason})
        else:
            ph = _phash(item["path"])
            duplicate = False
            if cfg.duplicate_filter_enabled:
                duplicate = any(_hamming(ph, prior) <= cfg.phash_hamming_threshold for prior in seen_hashes)
            if duplicate:
                rejected.append({**item, **q, "reason": "near_duplicate", "phash": f"{ph:016x}"})
            else:
                seen_hashes.append(ph)
                kept.append({**item, **q, "phash": f"{ph:016x}"})
        if progress:
            progress("quality", idx, max(1, len(candidates)), item["path"].name)

    if paths.standardized.exists():
        shutil.rmtree(paths.standardized)
    paths.standardized.mkdir(parents=True, exist_ok=True)

    for idx, row in enumerate(kept, start=1):
        name = f"ap_{idx:07d}.jpg"
        dst = paths.standardized / name
        with Image.open(row["path"]) as im:
            if im.mode != "RGB":
                im = im.convert("RGB")
            im.save(dst, quality=cfg.jpeg_quality)
        row["standardized_name"] = name
        row["standardized_path"] = (Path("work") / "standardized" / name).as_posix()

    assigned = _allocate_source_groups(kept, cfg)
    final_rows = []
    for split, rows in assigned.items():
        for row in rows:
            row["split"] = split
            final_rows.append(row)

    # Manifest
    fields = ["standardized_name", "standardized_path", "split", "source_id", "source_type", "original_path", "timestamp_seconds", "width", "height", "blur", "phash"]
    with paths.manifest.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in sorted(final_rows, key=lambda x: x["standardized_name"]):
            w.writerow({k: r.get(k, "") for k in fields})

    # Rebuild CVAT ZIPs and editable studio images
    ds = StudioDataset(paths.root)
    ds.dataset = {"version": 1, "classes": ["person"], "splits": {"train": [], "val": [], "test": []}}
    ds.annotations = {}
    for split in ("train", "val", "test"):
        split_rows = sorted(assigned[split], key=lambda x: x["standardized_name"])
        zp = paths.cvat_upload / f"{split}_images.zip"
        if zp.exists():
            zp.unlink()
        studio_dir = paths.studio_images / split
        if studio_dir.exists():
            shutil.rmtree(studio_dir)
        studio_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zp, "w", compression=zipfile.ZIP_DEFLATED) as z:
            for r in split_rows:
                src = paths.standardized / r["standardized_name"]
                z.write(src, arcname=r["standardized_name"])
                dst = studio_dir / r["standardized_name"]
                shutil.copy2(src, dst)
                ds.dataset["splits"][split].append({
                    "name": r["standardized_name"],
                    "path": dst.relative_to(paths.root).as_posix(),
                    "width": int(r["width"]), "height": int(r["height"]),
                    "source_id": r["source_id"], "source_type": r["source_type"],
                })
    ds.save()

    # Rejected report
    paths.reports.mkdir(parents=True, exist_ok=True)
    rej_path = paths.reports / "prepare_rejected.csv"
    rej_fields = ["reason", "source_id", "source_type", "original_path", "timestamp_seconds", "width", "height", "mean", "std", "blur"]
    with rej_path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=rej_fields)
        w.writeheader()
        for r in rejected:
            w.writerow({k: r.get(k, "") for k in rej_fields})

    summary = {s: len(assigned[s]) for s in ("train", "val", "test")}
    summary.update({"kept": len(kept), "rejected": len(rejected), "candidates": len(candidates)})
    say(f"Preparation complete: {summary}")
    return summary
