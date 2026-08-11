#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
STEP 3 - Aerial Person Detection Training
Shared standalone utilities embedded in this script.

Project invariants enforced here:
1) Target class is person only.
2) Training/validation use the Step-2 Development Pool only.
3) The frozen private Final Test is NEVER read for training, tuning, early stopping,
   augmentation design, threshold selection, or routine validation.
4) Dataset/split provenance, software/hardware environment, hyperparameters,
   checkpoints, metrics, timing, peak VRAM, hashes, and failure cases are archived.
5) Fixed-budget baseline defaults follow the project protocol:
   45 epochs, 1280 input, seed 42, AMP when CUDA is available.
   These are project controls for fair comparison, not claimed universal optima.
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import dataclasses
import hashlib
import importlib
import importlib.metadata
import json
import math
import os
import platform
import random
import shutil
import socket
import statistics
import subprocess
import sys
import time
import traceback
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

FORBIDDEN_TEST_TOKENS = (
    "90_final_test",
    "final-test",
    "final_test",
    "private_test",
    "private-test",
)
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}
SIZE_BUCKETS = {
    "tiny": (0.0, 16.0),
    "small": (16.0, 32.0),
    "medium": (32.0, 64.0),
    "large": (64.0, float("inf")),
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def timestamp_id() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_json(path: Path, data: Any) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def safe_copy(src: Path, dst: Path) -> Optional[Path]:
    if not src or not src.exists():
        return None
    ensure_dir(dst.parent)
    shutil.copy2(src, dst)
    return dst


def import_version(package_name: str) -> Optional[str]:
    try:
        return importlib.metadata.version(package_name)
    except Exception:
        return None


def git_info(path: Path) -> Dict[str, Any]:
    out = {"root": str(path), "commit": None, "dirty": None, "branch": None}
    try:
        root = subprocess.check_output(
            ["git", "-C", str(path), "rev-parse", "--show-toplevel"], text=True, stderr=subprocess.DEVNULL
        ).strip()
        out["root"] = root
        out["commit"] = subprocess.check_output(
            ["git", "-C", root, "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
        out["branch"] = subprocess.check_output(
            ["git", "-C", root, "rev-parse", "--abbrev-ref", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
        dirty = subprocess.check_output(
            ["git", "-C", root, "status", "--porcelain"], text=True, stderr=subprocess.DEVNULL
        )
        out["dirty"] = bool(dirty.strip())
    except Exception:
        pass
    return out


def run_command(command: Sequence[str], cwd: Optional[Path] = None, check: bool = True) -> subprocess.CompletedProcess:
    print("$", " ".join(map(str, command)), flush=True)
    return subprocess.run(list(map(str, command)), cwd=str(cwd) if cwd else None, check=check)


def running_in_colab() -> bool:
    return "COLAB_RELEASE_TAG" in os.environ or "google.colab" in sys.modules or Path("/content").exists() and Path("/content/drive").parent.exists()


def mount_google_drive_if_requested(enabled: bool) -> None:
    """Mount Google Drive automatically in Colab. Outside Colab this is a no-op."""
    if not enabled or not running_in_colab():
        return
    try:
        from google.colab import drive  # type: ignore
        mount_point = Path("/content/drive")
        if not (mount_point / "MyDrive").exists():
            drive.mount(str(mount_point), force_remount=False)
    except Exception as exc:
        raise RuntimeError(
            "Google Drive could not be mounted. In Colab, authorize Drive access and run the script again."
        ) from exc


def default_drive_output_root(project_root: Path) -> Path:
    """Return a persistent Google Drive output root in Colab, otherwise use the project-local runs directory."""
    drive_root = Path("/content/drive/MyDrive")
    if drive_root.exists():
        try:
            project_root.resolve().relative_to(drive_root.resolve())
            return project_root / "runs" / "step3"
        except Exception:
            return drive_root / "aerial_person_project" / "step3" / "runs"
    return project_root / "runs" / "step3"


def verify_l4_environment(device: str) -> Dict[str, Any]:
    """Record the active GPU and warn when the runtime is not the requested NVIDIA L4."""
    info: Dict[str, Any] = {"requested_training_gpu": "NVIDIA L4", "detected_gpu": None, "is_l4": False}
    try:
        import torch
        if device != "cpu" and torch.cuda.is_available():
            idx = int(str(device).split(":")[-1]) if ":" in str(device) else int(str(device))
            name = torch.cuda.get_device_name(idx)
            info["detected_gpu"] = name
            info["is_l4"] = "L4" in name.upper()
            print(f"Detected CUDA GPU: {name}")
            if not info["is_l4"]:
                print("WARNING: The Step-3 training protocol was requested for an NVIDIA L4, but a different GPU is active.")
        else:
            print("WARNING: CUDA is not available. Colab GPU acceleration must be enabled before final Step-3 training.")
    except Exception as exc:
        info["inspection_error"] = repr(exc)
    return info


def guard_not_final_test(*paths: Optional[Path]) -> None:
    for path in paths:
        if path is None:
            continue
        low = str(path).replace("\\", "/").lower()
        if any(token in low for token in FORBIDDEN_TEST_TOKENS):
            raise RuntimeError(
                f"Refusing to use a Final-Test-like path in Step 3: {path}\n"
                "The frozen private Final Test is reserved for Step 6 and must never be used here."
            )


AUTO_PATH_SENTINELS = {
    "", "auto", "none", "null", "detect", "discover", "automatic",
}

PLACEHOLDER_PATH_TOKENS = (
    "/path/to/",
    "\\path\\to\\",
    "path/to/your",
    "your_project",
    "your/project",
    "03_development_directory",
    "<project",
    "<path",
    "{project",
    "{path",
)


def is_auto_or_placeholder_path(value: Optional[str]) -> bool:
    if value is None:
        return True
    raw = str(value).strip()
    low = raw.lower().replace("\\", "/")
    if low in AUTO_PATH_SENTINELS:
        return True
    return any(token.replace("\\", "/") in low for token in PLACEHOLDER_PATH_TOKENS)


def _bounded_named_dirs(root: Path, target_name: str, max_depth: int = 7) -> List[Path]:
    """Find directories with a specific name without unbounded Google Drive recursion."""
    root = Path(root)
    if not root.exists() or not root.is_dir():
        return []
    hits: List[Path] = []
    base_depth = len(root.parts)
    skip_names = {
        ".git", ".ipynb_checkpoints", "__pycache__", "node_modules",
        "90_final_test_v1", "runs", "step3", "outputs",
    }
    for current, dirs, _files in os.walk(root):
        current_path = Path(current)
        depth = len(current_path.parts) - base_depth
        if depth >= max_depth:
            dirs[:] = []
            continue
        dirs[:] = [
            d for d in dirs
            if d not in skip_names and not d.startswith(".Trash")
        ]
        for d in list(dirs):
            if d == target_name:
                candidate = (current_path / d).resolve()
                low = str(candidate).replace("\\", "/").lower()
                if not any(token in low for token in FORBIDDEN_TEST_TOKENS):
                    hits.append(candidate)
                # No need to walk inside Development while locating it.
                with contextlib.suppress(ValueError):
                    dirs.remove(d)
    return hits


def _development_candidate_score(path: Path) -> int:
    """Score a Step-2 Development candidate by the artifacts required by Step 3."""
    path = Path(path)
    score = 0
    if path.name == "03_development":
        score += 20
    for p in [
        path / "train" / "images",
        path / "val" / "images",
        path / "images" / "train",
        path / "images" / "val",
    ]:
        if p.exists():
            score += 4
    parent = path.parent
    checks = [
        ("data.yaml", 8),
        ("dataset.yaml", 6),
        ("instances_train.json", 8),
        ("instances_val.json", 8),
        ("dataset_manifest.csv", 6),
        ("development_manifest.csv", 5),
        ("manifest.csv", 3),
    ]
    for name, points in checks:
        if (parent / name).exists() or any(parent.glob(f"*/{name}")):
            score += points
    return score


def _project_root_from_development(development_root: Path) -> Path:
    """Infer the Step-2 project root from the canonical Step-2 directory layout."""
    dev = Path(development_root).resolve()
    # Expected: <project>/workspace/aerial-person-data/03_development
    if dev.parent.name == "aerial-person-data" and dev.parent.parent.name == "workspace":
        return dev.parent.parent.parent.resolve()
    # Alternate: <project>/aerial-person-data/03_development
    if dev.parent.name == "aerial-person-data":
        return dev.parent.parent.resolve()
    return dev.parent.resolve()


def resolve_project_root_arg(explicit: Optional[str]) -> Path:
    """Use a valid explicit project root, otherwise auto-discover it safely."""
    if not is_auto_or_placeholder_path(explicit):
        p = Path(str(explicit)).expanduser()
        if p.exists():
            return p.resolve()
        print(
            f"WARNING: The configured project root does not exist: {p}. "
            "Falling back to automatic Google Drive discovery."
        )
    return discover_project_root()


def discover_project_root(start: Optional[Path] = None) -> Path:
    start = (start or Path.cwd()).resolve()

    standard_candidates = [
        Path("/content/drive/MyDrive/aerial_person_project"),
        Path("/content/drive/MyDrive/aerial_person_final_product"),
        Path("/content/drive/MyDrive/aerial-person-project"),
        Path("/content/drive/MyDrive/aerial-person-step2-pipeline"),
        Path("/content/drive/MyDrive/step2"),
    ]
    for p in standard_candidates:
        if p.exists() and (
            (p / "workspace" / "aerial-person-data" / "03_development").exists()
            or (p / "aerial-person-data" / "03_development").exists()
            or (p / "03_development").exists()
        ):
            return p.resolve()

    # First inspect the working directory and its parents.
    for p in [start, *start.parents]:
        if (
            (p / "workspace" / "aerial-person-data" / "03_development").exists()
            or (p / "aerial-person-data" / "03_development").exists()
            or (p / "03_development").exists()
        ):
            return p.resolve()

    # Bounded MyDrive search is the final Colab fallback.
    mydrive = Path("/content/drive/MyDrive")
    hits = _bounded_named_dirs(mydrive, "03_development", max_depth=7) if mydrive.exists() else []
    if hits:
        hits.sort(key=lambda p: (-_development_candidate_score(p), len(p.parts), str(p)))
        selected = hits[0]
        print(f"Auto-discovered Step-2 Development Pool: {selected}")
        return _project_root_from_development(selected)

    return start



def _looks_like_yolo_split_root(path: Path) -> bool:
    path = Path(path)
    patterns = [
        (
            path / "train" / "images",
            path / "train" / "labels",
            path / "val" / "images",
            path / "val" / "labels",
        ),
        (
            path / "images" / "train",
            path / "labels" / "train",
            path / "images" / "val",
            path / "labels" / "val",
        ),
    ]
    return any(all(p.exists() and p.is_dir() for p in group) for group in patterns)


def _looks_like_coco_root(path: Path) -> bool:
    path = Path(path)
    pairs = [
        (path / "instances_train.json", path / "instances_val.json"),
        (path / "annotations" / "instances_train.json", path / "annotations" / "instances_val.json"),
        (path / "coco" / "instances_train.json", path / "coco" / "instances_val.json"),
        (path / "coco" / "annotations" / "instances_train.json", path / "coco" / "annotations" / "instances_val.json"),
    ]
    return any(a.exists() and b.exists() for a, b in pairs)


def _looks_like_dataset_signature_root(path: Path) -> bool:
    path = Path(path)
    return (
        path.name == "03_development"
        or _looks_like_yolo_split_root(path)
        or _looks_like_coco_root(path)
        or (path / "data.yaml").exists()
        or (path / "dataset.yaml").exists()
    )


def _signature_candidate_score(path: Path) -> int:
    path = Path(path)
    score = 0
    if path.name == "03_development":
        score += 40
    if _looks_like_yolo_split_root(path):
        score += 35
    if _looks_like_coco_root(path):
        score += 35
    if (path / "data.yaml").exists():
        score += 20
    if (path / "dataset.yaml").exists():
        score += 15
    for n in ["dataset_manifest.csv", "development_manifest.csv", "manifest.csv"]:
        if (path / n).exists() or (path.parent / n).exists():
            score += 8
    low = str(path).replace("\\", "/").lower()
    if "03_development" in low:
        score += 10
    if "step2" in low or "aerial-person-data" in low:
        score += 4
    return score


def _bounded_signature_roots(root: Path, max_depth: int = 9, max_hits: int = 50) -> List[Path]:
    root = Path(root)
    if not root.exists() or not root.is_dir():
        return []

    hits: List[Path] = []
    seen = set()
    base_depth = len(root.parts)
    skip_names = {
        ".git", ".ipynb_checkpoints", "__pycache__", "node_modules",
        "90_final_test_v1", "final_test", "private_test",
        "runs", "step3", "outputs", ".Trash",
    }

    for current, dirs, _files in os.walk(root):
        current_path = Path(current)
        depth = len(current_path.parts) - base_depth
        if depth > max_depth:
            dirs[:] = []
            continue

        dirs[:] = [
            d for d in dirs
            if d not in skip_names
            and not d.startswith(".Trash")
            and "final_test" not in d.lower()
            and "private_test" not in d.lower()
        ]

        low = str(current_path).replace("\\", "/").lower()
        if any(token in low for token in FORBIDDEN_TEST_TOKENS):
            dirs[:] = []
            continue

        if _looks_like_dataset_signature_root(current_path):
            rp = current_path.resolve()
            key = str(rp)
            if key not in seen:
                seen.add(key)
                hits.append(rp)
                if len(hits) >= max_hits:
                    break

    hits.sort(key=lambda p: (-_signature_candidate_score(p), len(p.parts), str(p)))
    return hits


def _find_yolo_split_dirs(dataset_root: Path) -> Optional[Dict[str, Path]]:
    dataset_root = Path(dataset_root)
    layouts = [
        {
            "train_images": dataset_root / "train" / "images",
            "train_labels": dataset_root / "train" / "labels",
            "val_images": dataset_root / "val" / "images",
            "val_labels": dataset_root / "val" / "labels",
        },
        {
            "train_images": dataset_root / "images" / "train",
            "train_labels": dataset_root / "labels" / "train",
            "val_images": dataset_root / "images" / "val",
            "val_labels": dataset_root / "labels" / "val",
        },
    ]
    for layout in layouts:
        if all(p.exists() and p.is_dir() for p in layout.values()):
            return {k: v.resolve() for k, v in layout.items()}
    return None


def _parse_yolo_data_yaml_paths(data_yaml: Path) -> Optional[Dict[str, Path]]:
    try:
        import yaml
    except Exception as exc:
        print(f"WARNING: PyYAML is unavailable while parsing {data_yaml}: {exc}")
        return None

    data_yaml = Path(data_yaml).resolve()
    try:
        data = yaml.safe_load(data_yaml.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        print(f"WARNING: Could not parse {data_yaml}: {exc}")
        return None

    base = data_yaml.parent
    declared_path = data.get("path")
    if declared_path:
        p = Path(str(declared_path))
        if not p.is_absolute():
            p = (base / p).resolve()
        base = p

    def _resolve_entry(value):
        if not isinstance(value, str):
            return None
        p = Path(value)
        if not p.is_absolute():
            p = (base / p).resolve()
        return p

    train_images = _resolve_entry(data.get("train"))
    val_images = _resolve_entry(data.get("val"))
    if not train_images or not val_images:
        return None
    if not train_images.exists() or not val_images.exists():
        return None

    def _label_dir(image_dir: Path) -> Optional[Path]:
        image_dir = image_dir.resolve()
        parts = list(image_dir.parts)
        if image_dir.name == "images":
            candidate = image_dir.parent / "labels"
            if candidate.exists():
                return candidate.resolve()
        if image_dir.parent.name == "images":
            candidate = image_dir.parent.parent / "labels" / image_dir.name
            if candidate.exists():
                return candidate.resolve()
        idxs = [i for i, x in enumerate(parts) if x == "images"]
        if idxs:
            i = idxs[-1]
            candidate = Path(*parts[:i], "labels", *parts[i + 1:])
            if candidate.exists():
                return candidate.resolve()
        return None

    train_labels = _label_dir(train_images)
    val_labels = _label_dir(val_images)
    if not train_labels or not val_labels:
        return None

    return {
        "train_images": train_images.resolve(),
        "train_labels": train_labels.resolve(),
        "val_images": val_images.resolve(),
        "val_labels": val_labels.resolve(),
    }


def _find_data_yaml_near(dataset_root: Path) -> Optional[Path]:
    dataset_root = Path(dataset_root)
    for base in [dataset_root, dataset_root.parent]:
        for name in ["data.yaml", "dataset.yaml"]:
            p = base / name
            if p.exists():
                return p.resolve()
    for name in ["data.yaml", "dataset.yaml"]:
        hits = list(dataset_root.glob(f"**/{name}"))
        if hits:
            return hits[0].resolve()
    return None


def _discover_yolo_layout(dataset_root: Path) -> Optional[Dict[str, Path]]:
    direct = _find_yolo_split_dirs(dataset_root)
    if direct:
        return direct
    yml = _find_data_yaml_near(dataset_root)
    if yml:
        parsed = _parse_yolo_data_yaml_paths(yml)
        if parsed:
            parsed["data_yaml"] = yml
            return parsed
    return None


def _image_files(image_dir: Path) -> List[Path]:
    exts = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}
    return sorted(
        p.resolve()
        for p in Path(image_dir).rglob("*")
        if p.is_file() and p.suffix.lower() in exts
    )


def _convert_yolo_split_to_coco(
    image_dir: Path,
    label_dir: Path,
    out_json: Path,
    split_name: str,
) -> Path:
    from PIL import Image

    image_dir = Path(image_dir).resolve()
    label_dir = Path(label_dir).resolve()
    out_json = Path(out_json)
    out_json.parent.mkdir(parents=True, exist_ok=True)

    images = []
    annotations = []
    ann_id = 1
    object_count = 0
    bad_classes = set()
    malformed = []

    files = _image_files(image_dir)
    if not files:
        raise FileNotFoundError(f"No images found in YOLO {split_name} image directory: {image_dir}")

    for image_id, image_path in enumerate(files, start=1):
        with Image.open(image_path) as im:
            width, height = im.size

        rel = image_path.relative_to(image_dir)
        images.append({
            "id": image_id,
            "file_name": str(rel).replace("\\", "/"),
            "width": int(width),
            "height": int(height),
        })

        label_path = label_dir / rel.with_suffix(".txt")
        if not label_path.exists():
            continue

        lines = [x.strip() for x in label_path.read_text(encoding="utf-8-sig").splitlines() if x.strip()]
        for line_no, line in enumerate(lines, start=1):
            parts = line.split()
            if len(parts) < 5:
                malformed.append(f"{label_path}:{line_no}")
                continue
            try:
                cls = int(float(parts[0]))
                xc, yc, bw, bh = map(float, parts[1:5])
            except Exception:
                malformed.append(f"{label_path}:{line_no}")
                continue

            if cls != 0:
                bad_classes.add(cls)
                continue
            if not all(0.0 <= v <= 1.0 for v in [xc, yc, bw, bh]) or bw <= 0 or bh <= 0:
                malformed.append(f"{label_path}:{line_no}")
                continue

            x = (xc - bw / 2.0) * width
            y = (yc - bh / 2.0) * height
            w = bw * width
            h = bh * height

            x = max(0.0, min(float(width), x))
            y = max(0.0, min(float(height), y))
            w = max(0.0, min(float(width) - x, w))
            h = max(0.0, min(float(height) - y, h))
            if w <= 0 or h <= 0:
                malformed.append(f"{label_path}:{line_no}")
                continue

            annotations.append({
                "id": ann_id,
                "image_id": image_id,
                "category_id": 0,
                "bbox": [x, y, w, h],
                "area": w * h,
                "iscrowd": 0,
            })
            ann_id += 1
            object_count += 1

    if bad_classes:
        raise RuntimeError(
            f"YOLO {split_name} labels contain non-person class IDs: {sorted(bad_classes)}. "
            "Step 3 requires person-only class 0."
        )
    if malformed:
        raise RuntimeError(
            f"Malformed YOLO labels detected in {split_name}: {len(malformed)}. "
            f"Examples: {malformed[:5]}"
        )
    if object_count == 0:
        raise RuntimeError(
            f"No person annotations were found in YOLO {split_name} labels under {label_dir}. "
            "Training cannot start without labeled person instances."
        )

    payload = {
        "images": images,
        "annotations": annotations,
        "categories": [{"id": 0, "name": "person", "supercategory": "person"}],
        "info": {
            "description": f"Runtime COCO conversion for Step-3 {split_name}",
            "source_format": "YOLO person-only",
        },
    }
    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"Created runtime COCO {split_name}: {out_json} | "
        f"images={len(images)}, objects={object_count}"
    )
    return out_json.resolve()


def _runtime_coco_from_yolo(dataset_root: Path, split: str) -> Optional[Path]:
    layout = _discover_yolo_layout(dataset_root)
    if not layout:
        return None

    runtime_dir = Path(dataset_root) / "_step3_runtime_coco"
    if split == "train":
        return _convert_yolo_split_to_coco(
            layout["train_images"],
            layout["train_labels"],
            runtime_dir / "instances_train.json",
            "train",
        )
    return _convert_yolo_split_to_coco(
        layout["val_images"],
        layout["val_labels"],
        runtime_dir / "instances_val.json",
        "val",
    )


def discover_development_root(project_root: Path, explicit: Optional[str]) -> Path:
    if not is_auto_or_placeholder_path(explicit):
        p = Path(str(explicit)).expanduser()
        guard_not_final_test(p)
        if p.exists() and p.is_dir():
            if _looks_like_dataset_signature_root(p) or _discover_yolo_layout(p):
                print(f"Using explicit training dataset root: {p.resolve()}")
                return p.resolve()
            print(
                f"WARNING: The explicit development root exists but does not expose a recognized "
                f"train/val dataset layout: {p}. Falling back to automatic discovery."
            )
        else:
            print(
                f"WARNING: The configured development root does not exist: {p}. "
                "Falling back to automatic discovery."
            )

    candidates: List[Path] = []

    fixed = [
        project_root / "workspace" / "aerial-person-data" / "03_development",
        project_root / "aerial-person-data" / "03_development",
        project_root / "03_development",
        project_root / "dataset",
        project_root / "data",
        project_root,
    ]
    for c in fixed:
        if c.exists() and c.is_dir():
            low = str(c).replace("\\", "/").lower()
            if any(token in low for token in FORBIDDEN_TEST_TOKENS):
                continue
            if _looks_like_dataset_signature_root(c) or _discover_yolo_layout(c):
                candidates.append(c.resolve())

    candidates.extend(_bounded_signature_roots(project_root, max_depth=9))

    mydrive = Path("/content/drive/MyDrive")
    if mydrive.exists():
        candidates.extend(_bounded_signature_roots(mydrive, max_depth=9))

    unique: Dict[str, Path] = {}
    for p in candidates:
        rp = p.resolve()
        low = str(rp).replace("\\", "/").lower()
        if any(token in low for token in FORBIDDEN_TEST_TOKENS):
            continue
        unique[str(rp)] = rp

    valid = list(unique.values())
    valid.sort(key=lambda p: (-_signature_candidate_score(p), len(p.parts), str(p)))

    if valid:
        selected = valid[0]
        print(f"Using detected Step-2 training/validation dataset root: {selected}")
        print(f"Dataset signature score: {_signature_candidate_score(selected)}")
        if len(valid) > 1:
            print("Other detected train/val candidates:")
            for other in valid[1:6]:
                print(f"  - {other} (score={_signature_candidate_score(other)})")
        return selected

    raise FileNotFoundError(
        "Could not find any labeled Step-2 training/validation dataset in Google Drive. "
        "Accepted inputs are: canonical 03_development; YOLO train/images+train/labels and "
        "val/images+val/labels; YOLO images/train+labels/train and images/val+labels/val; "
        "a valid data.yaml; or COCO train/val JSONs. "
        "The private >=1000-image Final Test is NOT required and is intentionally ignored. "
        "If no candidate exists, Step 2 must be executed/finalized before Step 3 can train."
    )


def infer_project_root_from_development(development_root: Path, current_project_root: Path) -> Path:
    inferred = _project_root_from_development(development_root)
    if inferred.exists():
        return inferred
    return current_project_root

def discover_final_test_freeze(project_root: Path) -> Optional[Path]:
    candidates = [
        project_root / "workspace" / "aerial-person-data" / "90_final_test_v1" / "FREEZE.json",
        project_root / "aerial-person-data" / "90_final_test_v1" / "FREEZE.json",
        project_root / "90_final_test_v1" / "FREEZE.json",
    ]
    for c in candidates:
        if c.exists():
            return c.resolve()
    hits = list(project_root.rglob("FREEZE.json"))
    for h in hits:
        if "final" in str(h).lower() and "test" in str(h).lower():
            return h.resolve()
    return None


def require_frozen_final_test(project_root: Path, allow_missing: bool = True) -> Optional[Path]:
    """Discover Final-Test freeze metadata if present, but never require it for Step 3.

    The private >=1000-image dataset is reserved strictly for final testing. Step-3
    training must run normally even when that dataset has not been collected or
    frozen yet. Only FREEZE.json metadata is inspected when it exists; no Final-Test
    image or annotation is opened here.
    """
    freeze = discover_final_test_freeze(project_root)
    if freeze is None:
        print(
            "INFO: Private Final Test was not found. This is allowed in Step 3; "
            "training will continue using only the Step-2 Development Pool."
        )
        return None
    print(f"Private Final-Test freeze metadata found: {freeze}")
    print("Final-Test images/annotations will NOT be accessed during Step 3.")
    return freeze


def find_file(root: Path, names: Sequence[str]) -> Optional[Path]:
    for name in names:
        direct = root / name
        if direct.exists():
            return direct.resolve()
    for name in names:
        hits = list(root.rglob(name))
        if hits:
            return hits[0].resolve()
    return None


def discover_manifest(development_root: Path, explicit: Optional[str]) -> Optional[Path]:
    if not is_auto_or_placeholder_path(explicit):
        p = Path(str(explicit)).expanduser()
        guard_not_final_test(p)
        if p.exists():
            return p.resolve()
        print(f"WARNING: Manifest path not found: {p}. Falling back to automatic discovery.")
    return find_file(
        development_root.parent,
        ["dataset_manifest.csv", "development_manifest.csv", "manifest.csv"],
    )


def discover_data_yaml(development_root: Path, explicit: Optional[str]) -> Path:
    if not is_auto_or_placeholder_path(explicit):
        p = Path(str(explicit)).expanduser()
        guard_not_final_test(p)
        if p.exists():
            return p.resolve()
        print(f"WARNING: data.yaml path not found: {p}. Falling back to automatic discovery.")
    hit = find_file(development_root.parent, ["data.yaml", "dataset.yaml"])
    if not hit:
        raise FileNotFoundError("YOLO data.yaml not found. Pass --data-yaml explicitly.")
    guard_not_final_test(hit)
    return hit


def discover_coco_json(development_root: Path, split: str, explicit: Optional[str]) -> Path:
    if not is_auto_or_placeholder_path(explicit):
        p = Path(str(explicit)).expanduser()
        guard_not_final_test(p)
        if p.exists():
            return p.resolve()
        print(f"WARNING: COCO {split} path not found: {p}. Falling back to automatic discovery.")
    names = (
        ["instances_train.json", "train.json", "instances_train2017.json"]
        if split == "train"
        else ["instances_val.json", "val.json", "instances_val2017.json"]
    )
    hit = find_file(development_root.parent, names)
    if not hit:
        raise FileNotFoundError(f"COCO {split} JSON not found. Pass --coco-{split} explicitly.")
    guard_not_final_test(hit)
    return hit


def discover_split_image_dir(development_root: Path, split: str) -> Optional[Path]:
    """Locate the actual image directory for a Development split."""
    split = normalize_split(split)
    names = ["val", "valid", "validation"] if split == "val" else ["train", "training"]
    candidates: List[Path] = []
    for name in names:
        candidates.extend([
            development_root / name / "images",
            development_root / "images" / name,
            development_root / name,
        ])
    for p in candidates:
        if p.exists() and p.is_dir():
            # Prefer a directory that actually contains at least one supported image.
            try:
                if any(x.is_file() and x.suffix.lower() in IMAGE_EXTENSIONS for x in p.rglob("*")):
                    return p.resolve()
            except Exception:
                pass
    return None


def write_runtime_yolo_data_yaml(
    development_root: Path,
    out_path: Path,
    source_yaml: Optional[Path] = None,
) -> Path:
    """Write a Colab-safe YOLO YAML using discovered absolute POSIX paths.

    This avoids failures when a Step-2 data.yaml was originally generated on Windows
    and still contains drive-letter paths that are invalid inside Colab.
    """
    train_dir = discover_split_image_dir(development_root, "train")
    val_dir = discover_split_image_dir(development_root, "val")
    if train_dir is None or val_dir is None:
        if source_yaml and Path(source_yaml).exists():
            print(
                "WARNING: Could not reconstruct train/val image directories from the canonical "
                "03_development layout. The original data.yaml will be used unchanged."
            )
            return Path(source_yaml).resolve()
        raise FileNotFoundError(
            "Could not locate train/val image directories under the Step-2 Development Pool."
        )

    ensure_dir(out_path.parent)
    content = (
        f"train: {train_dir.as_posix()}\n"
        f"val: {val_dir.as_posix()}\n"
        "nc: 1\n"
        "names:\n"
        "  0: person\n"
    )
    out_path.write_text(content, encoding="utf-8")
    print(f"Colab-safe runtime YOLO data YAML: {out_path}")
    print(f"  train: {train_dir}")
    print(f"  val:   {val_dir}")
    return out_path.resolve()

def audit_yolo_labels(development_root: Path) -> Dict[str, Any]:
    """Validate YOLO label syntax and enforce class 0=person for train/internal-val."""
    report: Dict[str, Any] = {"splits": {}, "errors": []}
    for split in ("train", "val"):
        label_candidates = [
            development_root / split / "labels",
            development_root / "labels" / split,
        ]
        label_dir = next((p for p in label_candidates if p.exists() and p.is_dir()), None)
        image_dir = discover_split_image_dir(development_root, split)
        image_count = 0
        if image_dir is not None:
            image_count = sum(
                1 for p in image_dir.rglob("*")
                if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
            )
        label_files = list(label_dir.rglob("*.txt")) if label_dir else []
        box_count = 0
        for label_path in label_files:
            try:
                lines = label_path.read_text(encoding="utf-8-sig").splitlines()
            except Exception as exc:
                report["errors"].append(f"Unreadable label file {label_path}: {exc}")
                continue
            for line_no, line in enumerate(lines, start=1):
                line = line.strip()
                if not line:
                    continue
                parts = line.split()
                if len(parts) != 5:
                    report["errors"].append(
                        f"{label_path}:{line_no}: expected 5 YOLO fields, got {len(parts)}"
                    )
                    continue
                try:
                    cls = int(float(parts[0]))
                    vals = [float(x) for x in parts[1:]]
                except Exception:
                    report["errors"].append(
                        f"{label_path}:{line_no}: non-numeric YOLO label values"
                    )
                    continue
                if cls != 0:
                    report["errors"].append(
                        f"{label_path}:{line_no}: class {cls} found; Step 3 requires class 0=person only"
                    )
                if not all(0.0 <= v <= 1.0 for v in vals):
                    report["errors"].append(
                        f"{label_path}:{line_no}: normalized coordinates must be in [0,1]"
                    )
                if vals[2] <= 0.0 or vals[3] <= 0.0:
                    report["errors"].append(
                        f"{label_path}:{line_no}: width/height must be positive"
                    )
                box_count += 1
                if len(report["errors"]) >= 50:
                    break
            if len(report["errors"]) >= 50:
                break
        report["splits"][split] = {
            "image_dir": str(image_dir) if image_dir else None,
            "image_count": image_count,
            "label_dir": str(label_dir) if label_dir else None,
            "label_files": len(label_files),
            "boxes": box_count,
        }
    if report["errors"]:
        raise RuntimeError(
            "YOLO label audit failed. First errors:\n- " + "\n- ".join(report["errors"][:20])
        )
    return report

def load_manifest_rows(path: Optional[Path]) -> List[Dict[str, str]]:
    if not path or not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return [dict(r) for r in csv.DictReader(f)]


def first_existing_key(row: Mapping[str, Any], keys: Sequence[str]) -> Optional[str]:
    lower = {str(k).lower(): k for k in row.keys()}
    for key in keys:
        if key.lower() in lower:
            return str(lower[key.lower()])
    return None


def normalize_split(value: str) -> str:
    v = (value or "").strip().lower().replace("_", "-")
    aliases = {
        "training": "train",
        "tr": "train",
        "validation": "val",
        "valid": "val",
        "dev": "val",
        "internal-val": "val",
        "internal-validation": "val",
    }
    return aliases.get(v, v)


def audit_manifest(rows: List[Dict[str, str]]) -> Dict[str, Any]:
    if not rows:
        return {
            "available": False,
            "row_count": 0,
            "warnings": ["Manifest not available; dataset provenance checks are limited."],
        }

    sample = rows[0]
    split_key = first_existing_key(sample, ["split", "dataset_split"])
    group_key = first_existing_key(sample, ["group_id", "sequence_id", "flight_id", "site_id", "actor_id", "source_group"])
    source_key = first_existing_key(sample, ["source", "source_name", "dataset", "dataset_name"])
    person_key = first_existing_key(sample, ["person_count", "count_person", "num_persons", "num_objects"])
    class_key = first_existing_key(sample, ["class_name", "class", "target_class"])

    split_counts = Counter()
    source_counts = Counter()
    background_count = 0
    groups_by_split: Dict[str, set] = defaultdict(set)
    unexpected_classes = set()

    for r in rows:
        split = normalize_split(r.get(split_key, "")) if split_key else ""
        if split:
            split_counts[split] += 1
        if source_key:
            source_counts[r.get(source_key, "")] += 1
        if person_key:
            try:
                if float(r.get(person_key, "0") or 0) <= 0:
                    background_count += 1
            except Exception:
                pass
        if group_key and split:
            g = (r.get(group_key, "") or "").strip()
            if g:
                groups_by_split[split].add(g)
        if class_key:
            c = (r.get(class_key, "") or "").strip().lower()
            if c and c not in {"person", "0", "person-only", "human"}:
                unexpected_classes.add(c)

    leakage = []
    train_groups = groups_by_split.get("train", set())
    val_groups = groups_by_split.get("val", set())
    for g in sorted(train_groups.intersection(val_groups)):
        leakage.append(g)

    warnings = []
    if not split_key:
        warnings.append("No split column detected in manifest.")
    if not group_key:
        warnings.append("No group/sequence/site/flight/actor key detected; group leakage cannot be verified.")
    if leakage:
        warnings.append(f"CRITICAL: {len(leakage)} group IDs occur in both train and val.")
    if unexpected_classes:
        warnings.append(f"Unexpected class values observed: {sorted(unexpected_classes)[:20]}")

    return {
        "available": True,
        "row_count": len(rows),
        "columns": list(sample.keys()),
        "split_key": split_key,
        "group_key": group_key,
        "source_key": source_key,
        "person_count_key": person_key,
        "class_key": class_key,
        "split_counts": dict(split_counts),
        "source_counts": dict(source_counts),
        "background_images": background_count if person_key else None,
        "group_leakage_train_val": leakage[:100],
        "group_leakage_count": len(leakage),
        "unexpected_classes": sorted(unexpected_classes),
        "warnings": warnings,
    }


def assert_manifest_safe(audit: Mapping[str, Any], allow_missing_group_key: bool = False) -> None:
    if audit.get("group_leakage_count", 0):
        raise RuntimeError(
            f"Manifest preflight failed: {audit['group_leakage_count']} group IDs overlap train/val."
        )
    if audit.get("available") and not audit.get("group_key") and not allow_missing_group_key:
        raise RuntimeError(
            "Manifest does not expose a group-aware key (sequence/site/flight/actor/source_group). "
            "Pass --allow-missing-group-key only if the Step-2 split was independently verified."
        )
    if audit.get("unexpected_classes"):
        raise RuntimeError(
            f"Manifest contains unexpected target classes: {audit['unexpected_classes'][:10]}"
        )


def capture_environment() -> Dict[str, Any]:
    env: Dict[str, Any] = {
        "captured_utc": utc_now(),
        "hostname": socket.gethostname(),
        "platform": platform.platform(),
        "python": sys.version,
        "executable": sys.executable,
        "cpu": platform.processor(),
        "packages": {
            name: import_version(name)
            for name in [
                "torch",
                "torchvision",
                "ultralytics",
                "transformers",
                "albumentations",
                "pycocotools",
                "numpy",
                "pillow",
                "opencv-python",
                "matplotlib",
                "pandas",
            ]
        },
    }
    try:
        import torch
        env["torch"] = {
            "version": torch.__version__,
            "cuda_available": torch.cuda.is_available(),
            "cuda_version": torch.version.cuda,
            "cudnn_version": torch.backends.cudnn.version() if torch.backends.cudnn.is_available() else None,
        }
        if torch.cuda.is_available():
            env["gpus"] = []
            for i in range(torch.cuda.device_count()):
                p = torch.cuda.get_device_properties(i)
                env["gpus"].append(
                    {
                        "index": i,
                        "name": p.name,
                        "total_memory_bytes": p.total_memory,
                        "compute_capability": f"{p.major}.{p.minor}",
                    }
                )
    except Exception as exc:
        env["torch_error"] = repr(exc)

    try:
        smi = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=name,driver_version,memory.total", "--format=csv,noheader"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
        env["nvidia_smi"] = [line.strip() for line in smi.splitlines() if line.strip()]
    except Exception:
        env["nvidia_smi"] = None
    return env


def set_global_seed(seed: int, deterministic: bool = True) -> None:
    random.seed(seed)
    try:
        import numpy as np
        np.random.seed(seed)
    except Exception:
        pass
    try:
        import torch
        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
        if deterministic:
            torch.backends.cudnn.deterministic = True
            torch.backends.cudnn.benchmark = False
    except Exception:
        pass


def reset_peak_vram() -> None:
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.reset_peak_memory_stats()
            torch.cuda.synchronize()
    except Exception:
        pass


def peak_vram_mb() -> Optional[float]:
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.synchronize()
            return float(torch.cuda.max_memory_allocated() / (1024 ** 2))
    except Exception:
        pass
    return None


def cuda_sync() -> None:
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.synchronize()
    except Exception:
        pass


def count_parameters(model: Any) -> Dict[str, Optional[int]]:
    try:
        total = sum(int(p.numel()) for p in model.parameters())
        trainable = sum(int(p.numel()) for p in model.parameters() if p.requires_grad)
        return {"total": total, "trainable": trainable}
    except Exception:
        return {"total": None, "trainable": None}


def load_coco_json(path: Path) -> Dict[str, Any]:
    data = read_json(path)
    if not isinstance(data, dict) or "images" not in data or "annotations" not in data:
        raise ValueError(f"Not a COCO detection JSON: {path}")
    return data


def person_category_id(coco_data: Mapping[str, Any]) -> int:
    cats = list(coco_data.get("categories", []))
    for c in cats:
        if str(c.get("name", "")).lower() in {"person", "human", "pedestrian", "people"}:
            return int(c["id"])
    if len(cats) == 1:
        return int(cats[0]["id"])
    raise RuntimeError("Could not identify a unique person category in COCO JSON.")


def validate_person_only_coco(coco_data: Mapping[str, Any]) -> Dict[str, Any]:
    pid = person_category_id(coco_data)
    ann_cat_ids = {int(a.get("category_id", -999)) for a in coco_data.get("annotations", [])}
    unexpected = sorted(x for x in ann_cat_ids if x != pid)
    if unexpected:
        raise RuntimeError(f"COCO file is not person-only. Unexpected category IDs: {unexpected[:20]}")
    return {
        "person_category_id": pid,
        "images": len(coco_data.get("images", [])),
        "annotations": len(coco_data.get("annotations", [])),
        "categories": coco_data.get("categories", []),
    }


def build_image_index(search_root: Path) -> Dict[str, List[Path]]:
    index: Dict[str, List[Path]] = defaultdict(list)
    for p in search_root.rglob("*"):
        if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS:
            index[p.name].append(p.resolve())
    return index


def resolve_coco_image_paths(
    coco_data: Mapping[str, Any],
    search_root: Path,
    strict: bool = True,
) -> Dict[int, Path]:
    index = build_image_index(search_root)
    resolved: Dict[int, Path] = {}
    missing = []
    ambiguous = []
    for im in coco_data["images"]:
        image_id = int(im["id"])
        file_name = str(im["file_name"]).replace("\\", "/")
        direct_candidates = [
            search_root / file_name,
            search_root / "images" / file_name,
            search_root / "images" / "train" / Path(file_name).name,
            search_root / "images" / "val" / Path(file_name).name,
            search_root / "train" / "images" / Path(file_name).name,
            search_root / "val" / "images" / Path(file_name).name,
        ]
        found = next((p.resolve() for p in direct_candidates if p.exists()), None)
        if found is None:
            matches = index.get(Path(file_name).name, [])
            if len(matches) == 1:
                found = matches[0]
            elif len(matches) > 1:
                # Prefer candidate whose suffix components match COCO file_name.
                fn_parts = Path(file_name).parts
                scored = []
                for m in matches:
                    mp = m.parts
                    suffix_match = 0
                    for a, b in zip(reversed(mp), reversed(fn_parts)):
                        if a == b:
                            suffix_match += 1
                        else:
                            break
                    scored.append((suffix_match, m))
                scored.sort(key=lambda x: x[0], reverse=True)
                if scored and (len(scored) == 1 or scored[0][0] > scored[1][0]):
                    found = scored[0][1]
                else:
                    ambiguous.append(file_name)
        if found:
            guard_not_final_test(found)
            resolved[image_id] = found
        else:
            missing.append(file_name)
    if strict and (missing or ambiguous):
        raise FileNotFoundError(
            f"Could not resolve all COCO images. missing={len(missing)}, ambiguous={len(ambiguous)}. "
            f"Examples missing={missing[:5]}, ambiguous={ambiguous[:5]}"
        )
    return resolved


def xyxy_to_xywh(box: Sequence[float]) -> List[float]:
    x1, y1, x2, y2 = map(float, box)
    return [x1, y1, max(0.0, x2 - x1), max(0.0, y2 - y1)]


def box_iou_xywh(a: Sequence[float], b: Sequence[float]) -> float:
    ax, ay, aw, ah = map(float, a)
    bx, by, bw, bh = map(float, b)
    ax2, ay2 = ax + aw, ay + ah
    bx2, by2 = bx + bw, by + bh
    ix1, iy1 = max(ax, bx), max(ay, by)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    union = max(aw * ah + bw * bh - inter, 1e-12)
    return inter / union


def size_bucket_from_bbox(bbox_xywh: Sequence[float]) -> str:
    _, _, w, h = map(float, bbox_xywh)
    # Equivalent square side sqrt(area), so the per-object classification is
    # consistent with COCOeval area ranges [0,16^2), [16^2,32^2), ...
    characteristic = math.sqrt(max(w * h, 0.0))
    for name, (lo, hi) in SIZE_BUCKETS.items():
        if lo <= characteristic < hi:
            return name
    return "large"


def threshold_operating_metrics(
    coco_data: Mapping[str, Any],
    predictions: Sequence[Mapping[str, Any]],
    score_threshold: float = 0.25,
    iou_threshold: float = 0.50,
) -> Dict[str, Any]:
    pid = person_category_id(coco_data)
    gt_by_image: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    for ann in coco_data["annotations"]:
        if int(ann["category_id"]) == pid and not int(ann.get("iscrowd", 0)):
            gt_by_image[int(ann["image_id"])].append(dict(ann))
    pred_by_image: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    for p in predictions:
        if int(p["category_id"]) == pid and float(p["score"]) >= score_threshold:
            pred_by_image[int(p["image_id"])].append(dict(p))

    tp = fp = fn = 0
    bucket_gt = Counter()
    bucket_tp = Counter()
    per_image = []
    for im in coco_data["images"]:
        iid = int(im["id"])
        gts = gt_by_image.get(iid, [])
        preds = sorted(pred_by_image.get(iid, []), key=lambda x: float(x["score"]), reverse=True)
        matched = set()
        local_tp = 0
        for p in preds:
            best_iou = -1.0
            best_j = None
            for j, g in enumerate(gts):
                if j in matched:
                    continue
                iou = box_iou_xywh(p["bbox"], g["bbox"])
                if iou > best_iou:
                    best_iou, best_j = iou, j
            if best_j is not None and best_iou >= iou_threshold:
                matched.add(best_j)
                tp += 1
                local_tp += 1
                bucket_tp[size_bucket_from_bbox(gts[best_j]["bbox"])] += 1
            else:
                fp += 1
        local_fn = len(gts) - len(matched)
        fn += local_fn
        for g in gts:
            bucket_gt[size_bucket_from_bbox(g["bbox"])] += 1
        per_image.append(
            {
                "image_id": iid,
                "file_name": im.get("file_name"),
                "gt": len(gts),
                "pred": len(preds),
                "tp": local_tp,
                "fp": len(preds) - local_tp,
                "fn": local_fn,
                "error_score": local_fn * 3 + (len(preds) - local_tp),
            }
        )
    precision = tp / max(tp + fp, 1)
    recall = tp / max(tp + fn, 1)
    f1 = 2 * precision * recall / max(precision + recall, 1e-12)
    size_recall = {
        k: {
            "gt": int(bucket_gt[k]),
            "tp": int(bucket_tp[k]),
            "recall": float(bucket_tp[k] / max(bucket_gt[k], 1)),
        }
        for k in SIZE_BUCKETS
    }
    per_image.sort(key=lambda r: (r["error_score"], r["fn"], r["fp"]), reverse=True)
    return {
        "score_threshold": score_threshold,
        "iou_threshold": iou_threshold,
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "size_recall": size_recall,
        "worst_images": per_image[:200],
    }


def coco_eval_metrics(
    coco_json: Path,
    predictions_json: Path,
    max_dets: int = 1000,
) -> Dict[str, Any]:
    try:
        import numpy as np
        from pycocotools.coco import COCO
        from pycocotools.cocoeval import COCOeval
    except Exception as exc:
        return {"available": False, "error": f"pycocotools unavailable: {exc!r}"}

    coco_gt = COCO(str(coco_json))
    raw_preds = read_json(predictions_json)
    if not raw_preds:
        return {
            "available": True,
            "ap50_95": 0.0,
            "ap50": 0.0,
            "ar50_95": 0.0,
            "size_ap50_95": {k: 0.0 for k in SIZE_BUCKETS},
            "size_ap50": {k: 0.0 for k in SIZE_BUCKETS},
        }
    coco_dt = coco_gt.loadRes(raw_preds)
    pid = person_category_id(load_coco_json(coco_json))

    def run_area(lo_px: float, hi_px: float) -> Dict[str, float]:
        lo_area = 0.0 if lo_px <= 0 else lo_px * lo_px
        hi_area = 1e12 if math.isinf(hi_px) else hi_px * hi_px
        ev = COCOeval(coco_gt, coco_dt, "bbox")
        ev.params.catIds = [pid]
        ev.params.maxDets = [1, 100, max_dets]
        ev.params.areaRng = [[lo_area, hi_area]]
        ev.params.areaRngLbl = ["custom"]
        ev.evaluate()
        ev.accumulate()
        precision = ev.eval.get("precision")
        recall = ev.eval.get("recall")
        if precision is None or recall is None:
            return {"ap50_95": float("nan"), "ap50": float("nan"), "ar50_95": float("nan")}
        p_all = precision[:, :, 0, 0, 2]
        valid_all = p_all[p_all > -1]
        ap = float(valid_all.mean()) if valid_all.size else float("nan")
        p50 = precision[0, :, 0, 0, 2]
        valid50 = p50[p50 > -1]
        ap50 = float(valid50.mean()) if valid50.size else float("nan")
        r_all = recall[:, 0, 0, 2]
        valid_r = r_all[r_all > -1]
        ar = float(valid_r.mean()) if valid_r.size else float("nan")
        return {"ap50_95": ap, "ap50": ap50, "ar50_95": ar}

    overall = run_area(0.0, float("inf"))
    size = {name: run_area(lo, hi) for name, (lo, hi) in SIZE_BUCKETS.items()}
    return {
        "available": True,
        "ap50_95": overall["ap50_95"],
        "ap50": overall["ap50"],
        "ar50_95": overall["ar50_95"],
        "size_ap50_95": {k: v["ap50_95"] for k, v in size.items()},
        "size_ap50": {k: v["ap50"] for k, v in size.items()},
        "size_ar50_95": {k: v["ar50_95"] for k, v in size.items()},
        "max_dets": max_dets,
        "size_definition": "equivalent square side sqrt(box area): tiny<16, small[16,32), medium[32,64), large>=64 px",
    }


def save_operating_metrics_csv(path: Path, operating: Mapping[str, Any]) -> None:
    rows = operating.get("worst_images", [])
    if not rows:
        return
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def save_failure_visuals(
    coco_data: Mapping[str, Any],
    predictions: Sequence[Mapping[str, Any]],
    image_paths: Mapping[int, Path],
    operating: Mapping[str, Any],
    out_dir: Path,
    limit: int = 24,
    score_threshold: float = 0.25,
) -> None:
    try:
        from PIL import Image, ImageDraw
    except Exception:
        return
    ensure_dir(out_dir)
    pid = person_category_id(coco_data)
    gt_by_image: Dict[int, List[Mapping[str, Any]]] = defaultdict(list)
    pred_by_image: Dict[int, List[Mapping[str, Any]]] = defaultdict(list)
    for a in coco_data["annotations"]:
        if int(a["category_id"]) == pid:
            gt_by_image[int(a["image_id"])].append(a)
    for p in predictions:
        if int(p["category_id"]) == pid and float(p["score"]) >= score_threshold:
            pred_by_image[int(p["image_id"])].append(p)

    for rank, item in enumerate(operating.get("worst_images", [])[:limit], start=1):
        iid = int(item["image_id"])
        path = image_paths.get(iid)
        if not path or not path.exists():
            continue
        try:
            im = Image.open(path).convert("RGB")
            draw = ImageDraw.Draw(im)
            # Ground truth: solid rectangles; predictions: dashed-like double rectangles.
            for g in gt_by_image.get(iid, []):
                x, y, w, h = map(float, g["bbox"])
                draw.rectangle([x, y, x + w, y + h], width=3)
            for p in pred_by_image.get(iid, []):
                x, y, w, h = map(float, p["bbox"])
                draw.rectangle([x + 1, y + 1, x + w - 1, y + h - 1], width=1)
            dst = out_dir / f"{rank:03d}_id{iid}_{path.name}"
            im.save(dst, quality=92)
        except Exception:
            continue


def write_markdown_report(path: Path, report: Mapping[str, Any]) -> None:
    model = report.get("model", {})
    protocol = report.get("protocol", {})
    metrics = report.get("metrics", {})
    runtime = report.get("runtime", {})
    dataset = report.get("dataset", {})
    lines = [
        "# Step 3 Training Run Report",
        "",
        f"- Run ID: `{report.get('run_id')}`",
        f"- Model: `{model.get('name')}`",
        f"- Architecture role: {model.get('role')}",
        f"- Started UTC: `{report.get('started_utc')}`",
        f"- Finished UTC: `{report.get('finished_utc')}`",
        f"- Protocol: `{protocol.get('name')}`",
        f"- Epoch budget: `{protocol.get('epochs')}`",
        f"- Image size: `{protocol.get('imgsz')}`",
        f"- Batch size: `{protocol.get('batch')}`",
        f"- Seed: `{protocol.get('seed')}`",
        "",
        "## Dataset",
        f"- Development root: `{dataset.get('development_root')}`",
        f"- Manifest: `{dataset.get('manifest')}`",
        f"- Final-test freeze present: `{dataset.get('final_test_freeze_present')}`",
        "- Final Test accessed by this run: **NO**",
        "",
        "## Primary internal-validation metrics",
        f"- Precision@operating-point: `{metrics.get('precision')}`",
        f"- Recall@operating-point: `{metrics.get('recall')}`",
        f"- F1@operating-point: `{metrics.get('f1')}`",
        f"- AP50: `{metrics.get('ap50')}`",
        f"- mAP50-95: `{metrics.get('map50_95')}`",
        "",
        "## Size-aware validation",
    ]
    for k, v in (metrics.get("size_metrics") or {}).items():
        lines.append(f"- {k}: `{v}`")
    lines += [
        "",
        "## Runtime",
        f"- Training seconds: `{runtime.get('training_seconds')}`",
        f"- Peak allocated VRAM MB: `{runtime.get('peak_vram_mb')}`",
        f"- Cold latency ms/image: `{runtime.get('cold_latency_ms')}`",
        f"- Warm latency median ms/image: `{runtime.get('warm_latency_median_ms')}`",
        f"- Warm latency mean ms/image: `{runtime.get('warm_latency_mean_ms')}`",
        "",
        "## Reproducibility",
        f"- Best checkpoint SHA256: `{report.get('artifacts', {}).get('best_checkpoint_sha256')}`",
        f"- Last checkpoint SHA256: `{report.get('artifacts', {}).get('last_checkpoint_sha256')}`",
        "",
        "## Notes",
        "- This report uses only the Step-2 Development Pool and internal validation.",
        "- The frozen >=1000-image private Final Test remains sealed for Step 6.",
        "- Do not compare runs with different image sizes or materially different data/splits as if they were controlled baselines.",
    ]
    ensure_dir(path.parent)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def benchmark_latencies(callable_infer, warmup: int = 10, iterations: int = 50) -> Dict[str, Optional[float]]:
    times = []
    cuda_sync()
    t0 = time.perf_counter()
    callable_infer()
    cuda_sync()
    cold = (time.perf_counter() - t0) * 1000.0

    for _ in range(max(0, warmup)):
        callable_infer()
    cuda_sync()

    for _ in range(max(1, iterations)):
        t0 = time.perf_counter()
        callable_infer()
        cuda_sync()
        times.append((time.perf_counter() - t0) * 1000.0)
    return {
        "cold_latency_ms": cold,
        "warm_latency_mean_ms": statistics.mean(times) if times else None,
        "warm_latency_median_ms": statistics.median(times) if times else None,
        "warm_latency_p95_ms": sorted(times)[max(0, int(math.ceil(0.95 * len(times))) - 1)] if times else None,
        "latency_iterations": iterations,
        "latency_warmup": warmup,
    }


def checkpoint_record(path: Optional[Path]) -> Dict[str, Any]:
    if not path:
        return {"path": None, "sha256": None, "bytes": None}
    p = Path(path)
    if not p.exists():
        return {"path": str(p), "sha256": None, "bytes": None}
    return {"path": str(p.resolve()), "sha256": sha256_file(p), "bytes": p.stat().st_size}


def create_run_tree(output_root: Path, model_slug: str, run_name: Optional[str]) -> Tuple[str, Path, Dict[str, Path]]:
    # A stable default run name is intentional: rerunning the same Colab script can
    # discover the previous last.pt checkpoint in Google Drive and resume safely.
    run_id = run_name or "fixed_budget_baseline"
    root = output_root / model_slug / run_id
    sub = {
        "root": root,
        "audit": root / "00_audit",
        "config": root / "01_config",
        "checkpoints": root / "02_checkpoints",
        "metrics": root / "03_metrics",
        "curves": root / "04_curves",
        "predictions": root / "05_predictions",
        "failures": root / "06_failure_samples",
        "logs": root / "07_logs",
    }
    for p in sub.values():
        ensure_dir(p)
    ensure_dir(sub["checkpoints"] / "epochs")
    return run_id, root, sub


def append_jsonl(path: Path, record: Mapping[str, Any]) -> None:
    ensure_dir(path.parent)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(dict(record), ensure_ascii=False, default=str) + "\n")


def resolve_resume_checkpoint(run_root: Path, resume: Optional[str], ultralytics_layout: bool = False) -> Optional[Path]:
    """Resolve an explicit or automatic checkpoint without ever touching Final-Test paths."""
    value = (resume or "none").strip()
    if value.lower() in {"none", "false", "0", "off", "fresh"}:
        return None
    if value.lower() != "auto":
        p = Path(value).expanduser().resolve()
        guard_not_final_test(p)
        if not p.exists():
            raise FileNotFoundError(f"Resume checkpoint not found: {p}")
        return p

    candidates: List[Path] = [run_root / "02_checkpoints" / "last.pt"]
    if ultralytics_layout:
        candidates.insert(0, run_root / "trainer" / "weights" / "last.pt")
    for p in candidates:
        if p.exists():
            return p.resolve()

    epoch_dir = run_root / "02_checkpoints" / "epochs"
    if epoch_dir.exists():
        epoch_files = sorted(epoch_dir.glob("epoch_*.pt"))
        if epoch_files:
            return epoch_files[-1].resolve()
    return None


def record_dataset_snapshot(
    subdirs: Mapping[str, Path],
    development_root: Path,
    manifest: Optional[Path],
    data_files: Sequence[Path],
    final_freeze: Optional[Path],
    manifest_audit: Mapping[str, Any],
) -> Dict[str, Any]:
    records = []
    for p in [manifest, *data_files]:
        if p and Path(p).exists():
            pp = Path(p)
            guard_not_final_test(pp)
            records.append(
                {
                    "path": str(pp.resolve()),
                    "sha256": sha256_file(pp),
                    "bytes": pp.stat().st_size,
                }
            )
            safe_copy(pp, subdirs["audit"] / pp.name)
    freeze_rec = None
    if final_freeze and final_freeze.exists():
        # We hash/copy only the freeze metadata; we do NOT open Final-Test images/annotations.
        freeze_rec = {
            "path": str(final_freeze.resolve()),
            "sha256": sha256_file(final_freeze),
            "bytes": final_freeze.stat().st_size,
        }
        safe_copy(final_freeze, subdirs["audit"] / "FINAL_TEST_FREEZE_METADATA_ONLY.json")
    snapshot = {
        "development_root": str(development_root),
        "manifest": str(manifest) if manifest else None,
        "files": records,
        "manifest_audit": manifest_audit,
        "final_test_freeze_present": bool(final_freeze),
        "final_test_freeze_metadata": freeze_rec,
        "final_test_content_accessed": False,
    }
    write_json(subdirs["audit"] / "dataset_snapshot.json", snapshot)
    return snapshot


def save_args(path: Path, args: argparse.Namespace) -> None:
    write_json(path, vars(args))


def ensure_dependencies(required: Sequence[Tuple[str, str]]) -> None:
    """Install missing non-PyTorch dependencies automatically in Colab."""
    missing: List[str] = []
    for import_name, pip_name in required:
        try:
            importlib.import_module(import_name)
        except Exception:
            if import_name == "torch":
                raise RuntimeError(
                    "PyTorch is missing. Use a Google Colab GPU runtime, which provides a CUDA-enabled PyTorch build."
                )
            missing.append(pip_name)
    if not missing:
        return
    packages = sorted(set(missing))
    print("Installing missing Python dependencies:", " ".join(packages), flush=True)
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "-U", *packages])
    importlib.invalidate_caches()


def resolve_device(requested: str) -> str:
    requested = str(requested)
    if requested.lower() == "auto":
        try:
            import torch
            return "0" if torch.cuda.is_available() else "cpu"
        except Exception:
            return "cpu"
    return requested


def print_preflight_summary(
    model_name: str,
    development_root: Path,
    manifest: Optional[Path],
    freeze: Optional[Path],
    manifest_audit: Mapping[str, Any],
) -> None:
    print("\n" + "=" * 88)
    print("STEP 3 PREFLIGHT")
    print("=" * 88)
    print("Model:", model_name)
    print("Development Pool:", development_root)
    print("Manifest:", manifest)
    print("Frozen Final Test metadata:", freeze)
    print("Final Test content access:", "FORBIDDEN / NONE")
    print("Manifest rows:", manifest_audit.get("row_count"))
    print("Group key:", manifest_audit.get("group_key"))
    print("Group leakage train/val:", manifest_audit.get("group_leakage_count"))
    print("Split counts:", manifest_audit.get("split_counts"))
    print("Source counts:", manifest_audit.get("source_counts"))
    if manifest_audit.get("warnings"):
        print("Warnings:")
        for w in manifest_audit["warnings"]:
            print("  -", w)
    print("=" * 88 + "\n")


def make_base_parser(description: str) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=description, formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    p.add_argument("--project-root", type=str, default=None, help="Project root; auto-discovered when omitted.")
    p.add_argument("--development-root", type=str, default=None, help="Step-2 03_development directory.")
    p.add_argument("--manifest", type=str, default=None, help="Step-2 dataset_manifest.csv.")
    p.add_argument(
        "--output-root", type=str, default=None,
        help="Root for Step-3 artifacts. In Colab the default is Google Drive: /content/drive/MyDrive/aerial_person_project/step3/runs.",
    )
    p.add_argument(
        "--run-name", type=str, default=None,
        help="Persistent experiment name. The default fixed_budget_baseline is intentionally stable for automatic resume.",
    )
    p.add_argument(
        "--mount-drive", action=argparse.BooleanOptionalAction, default=True,
        help="Automatically mount Google Drive when running in Colab.",
    )
    p.add_argument(
        "--allow-missing-final-test-freeze", action="store_true", default=True,
        help="Compatibility option. Step 3 always allows the private Final Test to be absent and never reads its content.",
    )
    p.add_argument("--allow-missing-group-key", action="store_true",
                   help="Use only if Step-2 group-aware split was independently verified.")
    p.add_argument("--epochs", type=int, default=45, help="Fixed-budget baseline epoch count.")
    p.add_argument("--imgsz", type=int, default=1280, help="Fixed-budget baseline square input size.")
    p.add_argument("--batch", type=int, default=2, help="Batch size. Keep the value fixed when feasible.")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--device", type=str, default="auto")
    p.add_argument("--operating-conf", type=float, default=0.25,
                   help="Only for descriptive P/R/F1 and failure analysis on internal validation.")
    p.add_argument("--operating-iou", type=float, default=0.50)
    p.add_argument("--max-det", type=int, default=1000)
    p.add_argument("--latency-warmup", type=int, default=10)
    p.add_argument("--latency-iters", type=int, default=50)
    p.add_argument("--failure-visuals", type=int, default=24)
    p.add_argument("--dry-run", action="store_true", help="Run data/config preflight without training.")
    return p



MODEL_NAME = "YOLO26s"
MODEL_SLUG = "yolo26s"
MODEL_ROLE = "Product-oriented real-time baseline selected in Step 1"
PRETRAINED_DEFAULT = "yolo26s.pt"
REFERENCE_URL = "https://docs.ultralytics.com/models/yolo26/"


def _mean_or_none(value: Any) -> Optional[float]:
    try:
        import numpy as np
        arr = np.asarray(value, dtype=float)
        return float(arr.mean()) if arr.size else None
    except Exception:
        try:
            return float(value)
        except Exception:
            return None


def export_ultralytics_predictions_to_coco(
    model: Any,
    coco_json: Path,
    development_root: Path,
    imgsz: int,
    device: str,
    max_det: int,
    out_json: Path,
) -> Tuple[List[Dict[str, Any]], Dict[int, Path]]:
    coco = load_coco_json(coco_json)
    pid = person_category_id(coco)
    image_paths = resolve_coco_image_paths(coco, development_root, strict=True)
    predictions: List[Dict[str, Any]] = []

    ordered_images = sorted(coco["images"], key=lambda x: int(x["id"]))
    for idx, im in enumerate(ordered_images, start=1):
        iid = int(im["id"])
        path = image_paths[iid]
        results = model.predict(
            source=str(path),
            imgsz=imgsz,
            device=device,
            conf=0.001,
            iou=0.70,
            max_det=max_det,
            verbose=False,
            stream=False,
        )
        if not results:
            continue
        result = results[0]
        boxes = getattr(result, "boxes", None)
        if boxes is not None and len(boxes):
            xyxy = boxes.xyxy.detach().cpu().numpy()
            conf = boxes.conf.detach().cpu().numpy()
            cls = boxes.cls.detach().cpu().numpy()
            for b, s, c in zip(xyxy, conf, cls):
                if int(round(float(c))) != 0:
                    continue
                predictions.append(
                    {
                        "image_id": iid,
                        "category_id": pid,
                        "bbox": [float(x) for x in xyxy_to_xywh(b.tolist())],
                        "score": float(s),
                    }
                )
        if idx % 100 == 0 or idx == len(ordered_images):
            print(f"[COCO export] {idx}/{len(ordered_images)} internal-val images", flush=True)

    write_json(out_json, predictions)
    return predictions, image_paths


def main() -> None:
    parser = make_base_parser(
        "Train the final Step-3 YOLO26s baseline with complete reproducibility and reporting artifacts."
    )
    parser.add_argument("--data-yaml", type=str, default=None)
    parser.add_argument("--coco-val", type=str, default=None,
                        help="COCO internal-validation JSON used only for standardized reporting.")
    parser.add_argument("--pretrained", type=str, default=PRETRAINED_DEFAULT)
    parser.add_argument("--optimizer", type=str, default="auto",
                        help="Ultralytics optimizer. 'auto' preserves the official fine-tuning behavior.")
    parser.add_argument("--lr0", type=float, default=None,
                        help="Optional explicit initial LR. Omit to let the selected optimizer recipe resolve it.")
    parser.add_argument("--lrf", type=float, default=None)
    parser.add_argument("--weight-decay", type=float, default=None)
    parser.add_argument("--cos-lr", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--amp", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--deterministic", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--mosaic", type=float, default=0.50,
                        help="Conservative project baseline; ablate separately rather than claiming global optimality.")
    parser.add_argument("--mixup", type=float, default=0.00)
    parser.add_argument("--copy-paste", type=float, default=0.00)
    parser.add_argument("--close-mosaic", type=int, default=10)
    parser.add_argument("--degrees", type=float, default=5.0)
    parser.add_argument("--translate", type=float, default=0.08)
    parser.add_argument("--scale", type=float, default=0.35)
    parser.add_argument("--shear", type=float, default=0.0)
    parser.add_argument("--perspective", type=float, default=0.0)
    parser.add_argument("--fliplr", type=float, default=0.50)
    parser.add_argument("--flipud", type=float, default=0.0)
    parser.add_argument("--hsv-h", type=float, default=0.01)
    parser.add_argument("--hsv-s", type=float, default=0.30)
    parser.add_argument("--hsv-v", type=float, default=0.20)
    parser.add_argument("--save-period", type=int, default=1, help="Save an Ultralytics checkpoint after every epoch to Google Drive.")
    parser.add_argument("--resume", type=str, default="auto", help="auto = resume from this run's Drive last.pt when available; none = start fresh; or provide an explicit checkpoint path.")
    args = parser.parse_args()

    mount_google_drive_if_requested(args.mount_drive)
    project_root = resolve_project_root_arg(args.project_root)
    development_root = discover_development_root(project_root, args.development_root)
    project_root = infer_project_root_from_development(development_root, project_root)
    manifest = discover_manifest(development_root, args.manifest)
    data_yaml = discover_data_yaml(development_root, args.data_yaml)
    coco_val = discover_coco_json(development_root, "val", args.coco_val)
    guard_not_final_test(development_root, manifest, data_yaml, coco_val)
    freeze = require_frozen_final_test(project_root, args.allow_missing_final_test_freeze)

    rows = load_manifest_rows(manifest)
    manifest_audit = audit_manifest(rows)
    assert_manifest_safe(manifest_audit, args.allow_missing_group_key)

    coco_val_data = load_coco_json(coco_val)
    coco_val_summary = validate_person_only_coco(coco_val_data)
    val_image_paths = resolve_coco_image_paths(coco_val_data, development_root, strict=True)
    yolo_label_audit = audit_yolo_labels(development_root)

    print_preflight_summary(MODEL_NAME, development_root, manifest, freeze, manifest_audit)
    print("COCO internal-val:", coco_val_summary)
    print("Resolved internal-val images:", len(val_image_paths))
    print("YOLO label audit:", yolo_label_audit)
    if args.dry_run:
        print("Dry run complete. No training was started.")
        return

    ensure_dependencies([
        ("torch", "torch"),
        ("ultralytics", "ultralytics==8.4.116"),
        ("pycocotools", "pycocotools"),
        ("PIL", "pillow"),
        ("numpy", "numpy"),
        ("matplotlib", "matplotlib"),
    ])

    import torch
    from ultralytics import YOLO

    device = resolve_device(args.device)
    gpu_audit = verify_l4_environment(device)
    set_global_seed(args.seed, args.deterministic)

    output_root = (
        Path(args.output_root).expanduser().resolve()
        if args.output_root
        else default_drive_output_root(project_root)
    )
    run_id, run_root, sub = create_run_tree(output_root, MODEL_SLUG, args.run_name)
    started_utc = utc_now()
    save_args(sub["config"] / "cli_args.json", args)
    env = capture_environment()
    env["project_git"] = git_info(project_root)
    env["training_gpu_audit"] = gpu_audit
    write_json(sub["audit"] / "environment.json", env)
    dataset_snapshot = record_dataset_snapshot(
        sub, development_root, manifest, [data_yaml, coco_val], freeze, manifest_audit
    )
    runtime_data_yaml = write_runtime_yolo_data_yaml(
        development_root,
        sub["config"] / "runtime_data_colab.yaml",
        source_yaml=data_yaml,
    )

    protocol = {
        "name": "step3_fixed_budget_baseline",
        "target_class": "person",
        "epochs": args.epochs,
        "imgsz": args.imgsz,
        "batch": args.batch,
        "seed": args.seed,
        "device": device,
        "amp": args.amp,
        "optimizer": args.optimizer,
        "lr0": args.lr0,
        "lrf": args.lrf,
        "weight_decay": args.weight_decay,
        "cos_lr": args.cos_lr,
        "augmentation": {
            "mosaic": args.mosaic,
            "mixup": args.mixup,
            "copy_paste": args.copy_paste,
            "close_mosaic": args.close_mosaic,
            "degrees": args.degrees,
            "translate": args.translate,
            "scale": args.scale,
            "shear": args.shear,
            "perspective": args.perspective,
            "fliplr": args.fliplr,
            "flipud": args.flipud,
            "hsv_h": args.hsv_h,
            "hsv_s": args.hsv_s,
            "hsv_v": args.hsv_v,
        },
        "fairness_note": (
            "45 epochs / 1280 / fixed split / seed are project controls. "
            "Augmentation values are conservative project baseline defaults and must be reported as such."
        ),
        "tiling": False,
        "p2_modification": False,
        "final_test_used": False,
        "private_final_test_required_for_step3": False,
        "checkpoint_policy": "save every completed epoch to persistent Google Drive storage",
        "runtime_data_yaml": str(runtime_data_yaml),
        "default_colab_output_root": str(default_drive_output_root(project_root)),
        "requested_training_hardware": "Google Colab NVIDIA L4 GPU",
    }
    write_json(sub["config"] / "resolved_protocol.json", protocol)

    model_meta = {
        "name": MODEL_NAME,
        "slug": MODEL_SLUG,
        "role": MODEL_ROLE,
        "pretrained": args.pretrained,
        "reference_url": REFERENCE_URL,
        "architecture_modification": "none",
        "p2_enabled": False,
        "tiling_enabled": False,
    }
    write_json(sub["config"] / "model_metadata.json", model_meta)

    resume_path = resolve_resume_checkpoint(run_root, args.resume, ultralytics_layout=True)
    if resume_path is not None:
        print(f"Resuming YOLO26s training from Google Drive checkpoint: {resume_path}")
        model = YOLO(str(resume_path))
        append_jsonl(
            sub["audit"] / "resume_history.jsonl",
            {"utc": utc_now(), "mode": "resume", "checkpoint": str(resume_path)},
        )
    else:
        print(f"Starting YOLO26s from pretrained checkpoint: {args.pretrained}")
        model = YOLO(args.pretrained)
        append_jsonl(
            sub["audit"] / "resume_history.jsonl",
            {"utc": utc_now(), "mode": "fresh", "checkpoint": args.pretrained},
        )

    train_kwargs: Dict[str, Any] = dict(
        data=str(runtime_data_yaml),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        workers=args.workers,
        device=device,
        seed=args.seed,
        deterministic=args.deterministic,
        single_cls=True,
        amp=args.amp,
        optimizer=args.optimizer,
        cos_lr=args.cos_lr,
        mosaic=args.mosaic,
        mixup=args.mixup,
        copy_paste=args.copy_paste,
        close_mosaic=args.close_mosaic,
        degrees=args.degrees,
        translate=args.translate,
        scale=args.scale,
        shear=args.shear,
        perspective=args.perspective,
        fliplr=args.fliplr,
        flipud=args.flipud,
        hsv_h=args.hsv_h,
        hsv_s=args.hsv_s,
        hsv_v=args.hsv_v,
        patience=max(args.epochs + 10, 1000),
        save=True,
        save_period=args.save_period,
        plots=True,
        cache=False,
        rect=False,
        multi_scale=False,
        max_det=args.max_det,
        project=str(run_root),
        name="trainer",
        exist_ok=True,
        verbose=True,
    )
    if args.lr0 is not None:
        train_kwargs["lr0"] = args.lr0
    if args.lrf is not None:
        train_kwargs["lrf"] = args.lrf
    if args.weight_decay is not None:
        train_kwargs["weight_decay"] = args.weight_decay
    if resume_path is not None:
        # Official Ultralytics resume flow: load last.pt first, then train(resume=True).
        # The loaded checkpoint restores optimizer, scheduler, scaler, and epoch state.
        train_kwargs["resume"] = True

    write_json(sub["config"] / "train_kwargs.json", train_kwargs)

    reset_peak_vram()
    train_start = time.perf_counter()
    try:
        model.train(**train_kwargs)
    except Exception:
        (sub["logs"] / "TRAINING_EXCEPTION.txt").write_text(traceback.format_exc(), encoding="utf-8")
        raise
    cuda_sync()
    training_seconds = time.perf_counter() - train_start
    peak_mb = peak_vram_mb()

    trainer = getattr(model, "trainer", None)
    trainer_save_dir = Path(getattr(trainer, "save_dir", run_root / "trainer"))
    best_path = Path(getattr(trainer, "best", trainer_save_dir / "weights" / "best.pt"))
    last_path = Path(getattr(trainer, "last", trainer_save_dir / "weights" / "last.pt"))
    best_copy = safe_copy(best_path, sub["checkpoints"] / "best.pt") or best_path
    last_copy = safe_copy(last_path, sub["checkpoints"] / "last.pt") or last_path

    for candidate in [
        "results.csv", "results.png", "PR_curve.png", "F1_curve.png", "P_curve.png",
        "R_curve.png", "confusion_matrix.png", "confusion_matrix_normalized.png",
        "labels.jpg", "labels_correlogram.jpg", "args.yaml",
    ]:
        src = trainer_save_dir / candidate
        if src.exists():
            target_dir = sub["metrics"] if src.suffix == ".csv" else sub["curves"]
            safe_copy(src, target_dir / src.name)

    eval_model = YOLO(str(best_copy))
    val_result = eval_model.val(
        data=str(data_yaml),
        split="val",
        imgsz=args.imgsz,
        batch=args.batch,
        workers=args.workers,
        device=device,
        single_cls=True,
        conf=0.001,
        iou=0.70,
        max_det=args.max_det,
        plots=True,
        save_json=True,
        project=str(run_root),
        name="final_internal_val",
        exist_ok=True,
        verbose=True,
    )

    pred_json = sub["predictions"] / "internal_val_predictions.coco.json"
    predictions, image_paths = export_ultralytics_predictions_to_coco(
        eval_model, coco_val, development_root, args.imgsz, device, args.max_det, pred_json
    )
    coco_data = load_coco_json(coco_val)
    validate_person_only_coco(coco_data)
    standardized = coco_eval_metrics(coco_val, pred_json, max_dets=args.max_det)
    operating = threshold_operating_metrics(
        coco_data, predictions, args.operating_conf, args.operating_iou
    )
    write_json(sub["metrics"] / "standardized_coco_metrics.json", standardized)
    write_json(sub["metrics"] / "operating_point_metrics.json", operating)
    save_operating_metrics_csv(sub["metrics"] / "failure_ranking.csv", operating)
    save_failure_visuals(
        coco_data, predictions, image_paths, operating, sub["failures"],
        limit=args.failure_visuals, score_threshold=args.operating_conf
    )

    best_epoch = None
    native_results_csv = sub["metrics"] / "results.csv"
    if native_results_csv.exists():
        try:
            import pandas as pd
            df = pd.read_csv(native_results_csv)
            metric_cols = [
                c for c in df.columns
                if "metrics/mAP50-95" in c or "metrics/mAP50-95(B)" in c or "map50-95" in c.lower()
            ]
            if metric_cols:
                best_idx = int(df[metric_cols[0]].astype(float).idxmax())
                epoch_col = next((c for c in df.columns if c.strip().lower() == "epoch"), None)
                best_epoch = int(df.loc[best_idx, epoch_col]) if epoch_col else best_idx
        except Exception:
            pass

    first_iid = int(coco_data["images"][0]["id"])
    latency_image = image_paths[first_iid]
    latency = benchmark_latencies(
        lambda: eval_model.predict(
            source=str(latency_image), imgsz=args.imgsz, device=device,
            conf=0.25, iou=0.70, max_det=args.max_det, verbose=False
        ),
        warmup=args.latency_warmup,
        iterations=args.latency_iters,
    )

    native_box = getattr(val_result, "box", None)
    native_metrics = {
        "map50_95": _mean_or_none(getattr(native_box, "map", None)) if native_box is not None else None,
        "ap50": _mean_or_none(getattr(native_box, "map50", None)) if native_box is not None else None,
        "precision": _mean_or_none(getattr(native_box, "mp", None)) if native_box is not None else None,
        "recall": _mean_or_none(getattr(native_box, "mr", None)) if native_box is not None else None,
    }

    metrics = {
        "primary_source": "standardized COCO internal-validation evaluation",
        "map50_95": standardized.get("ap50_95"),
        "ap50": standardized.get("ap50"),
        "precision": operating.get("precision"),
        "recall": operating.get("recall"),
        "f1": operating.get("f1"),
        "size_metrics": {
            k: {
                "ap50_95": standardized.get("size_ap50_95", {}).get(k),
                "ap50": standardized.get("size_ap50", {}).get(k),
                "recall_at_operating_point": operating.get("size_recall", {}).get(k, {}).get("recall"),
                "gt_count": operating.get("size_recall", {}).get(k, {}).get("gt"),
            }
            for k in SIZE_BUCKETS
        },
        "ultralytics_native_metrics": native_metrics,
        "operating_conf": args.operating_conf,
        "operating_iou": args.operating_iou,
    }

    best_rec = checkpoint_record(Path(best_copy))
    last_rec = checkpoint_record(Path(last_copy))
    report = {
        "schema_version": "step3-run-report-v1",
        "run_id": run_id,
        "started_utc": started_utc,
        "finished_utc": utc_now(),
        "model": model_meta,
        "protocol": protocol,
        "dataset": dataset_snapshot,
        "environment": env,
        "training": {
            "best_epoch": best_epoch,
            "selection_metric": "internal validation mAP50-95",
            "fixed_budget_completed": True,
            "trainer_save_dir": str(trainer_save_dir),
        },
        "metrics": metrics,
        "runtime": {
            "training_seconds": training_seconds,
            "training_hours": training_seconds / 3600.0,
            "peak_vram_mb": peak_mb,
            **latency,
            "latency_scope": "single-image API call: preprocess + inference + postprocess; no video decode/render",
            "latency_image": str(latency_image),
        },
        "complexity": {
            "parameters": count_parameters(getattr(eval_model, "model", eval_model)),
            "flops": "Use Ultralytics model.info()/profile output archived in logs; value depends on input size.",
        },
        "artifacts": {
            "best_checkpoint": best_rec,
            "last_checkpoint": last_rec,
            "best_checkpoint_sha256": best_rec.get("sha256"),
            "last_checkpoint_sha256": last_rec.get("sha256"),
            "predictions_json": str(pred_json),
            "standardized_metrics_json": str(sub["metrics"] / "standardized_coco_metrics.json"),
            "failure_ranking_csv": str(sub["metrics"] / "failure_ranking.csv"),
        },
        "scientific_notes": [
            "YOLO26s is trained without P2 or tiling in the primary baseline, as fixed in Step 1.",
            "The private Final Test is not read in Step 3.",
            "Final deployment TensorRT benchmarking belongs to Step 4, not this training script.",
        ],
    }
    write_json(run_root / "STEP3_RUN_REPORT.json", report)
    write_markdown_report(run_root / "STEP3_RUN_REPORT.md", report)

    print("\nTraining complete.")
    print("Run directory:", run_root)
    print("Primary internal-val mAP50-95:", metrics["map50_95"])
    print("Primary internal-val AP50:", metrics["ap50"])
    print("Internal-val Recall@operating-point:", metrics["recall"])
    print("Peak VRAM MB:", peak_mb)
    print("Warm median latency ms:", latency.get("warm_latency_median_ms"))
    print("Best checkpoint:", best_copy)
    print("Private Final Test content accessed: NO (presence is optional in Step 3)")


if __name__ == "__main__":
    main()
