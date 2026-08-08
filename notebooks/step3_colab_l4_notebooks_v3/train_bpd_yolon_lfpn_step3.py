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


def discover_project_root(start: Optional[Path] = None) -> Path:
    start = (start or Path.cwd()).resolve()

    # Colab-first locations. These checks are intentionally shallow so that the
    # script does not recursively scan the user's entire Google Drive.
    colab_candidates = [
        Path("/content/drive/MyDrive/aerial_person_project"),
        Path("/content/drive/MyDrive/aerial_person_final_product"),
        Path("/content/drive/MyDrive/aerial-person-project"),
        Path("/content/drive/MyDrive/aerial-person-step2-pipeline"),
        Path("/content/drive/MyDrive/step2"),
    ]
    mydrive = Path("/content/drive/MyDrive")
    if mydrive.exists():
        try:
            colab_candidates.extend([p for p in mydrive.iterdir() if p.is_dir()])
        except Exception:
            pass
    for p in colab_candidates:
        if p.exists() and (
            (p / "workspace" / "aerial-person-data" / "03_development").exists()
            or (p / "aerial-person-data" / "03_development").exists()
            or (p / "03_development").exists()
            or (p / "workspace").exists()
            or (p / ".git").exists()
        ):
            return p.resolve()

    candidates = [start] + list(start.parents)
    markers = ("aerial-person-step2-pipeline", "workspace", ".git")
    for p in candidates:
        if any((p / m).exists() for m in markers):
            return p
    return start


def discover_development_root(project_root: Path, explicit: Optional[str]) -> Path:
    if explicit:
        p = Path(explicit).expanduser().resolve()
        guard_not_final_test(p)
        if not p.exists():
            raise FileNotFoundError(f"Development root not found: {p}")
        return p

    candidates = [
        project_root / "workspace" / "aerial-person-data" / "03_development",
        project_root / "aerial-person-data" / "03_development",
        project_root / "03_development",
        Path("/content/drive/MyDrive/aerial_person_project/workspace/aerial-person-data/03_development"),
        Path("/content/drive/MyDrive/aerial_person_project/aerial-person-data/03_development"),
        Path("/content/drive/MyDrive/aerial_person_project/03_development"),
    ]
    for c in candidates:
        if c.exists():
            guard_not_final_test(c)
            return c.resolve()

    # Controlled fallback: search only for directory name.
    hits = [p for p in project_root.rglob("03_development") if p.is_dir()]
    hits = [p for p in hits if not any(t in str(p).lower() for t in FORBIDDEN_TEST_TOKENS)]
    if hits:
        return hits[0].resolve()
    raise FileNotFoundError(
        "Could not locate the Step-2 Development Pool. Pass --development-root explicitly."
    )


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
    if explicit:
        p = Path(explicit).expanduser().resolve()
        guard_not_final_test(p)
        if not p.exists():
            raise FileNotFoundError(p)
        return p
    return find_file(
        development_root.parent,
        ["dataset_manifest.csv", "development_manifest.csv", "manifest.csv"],
    )


def discover_data_yaml(development_root: Path, explicit: Optional[str]) -> Path:
    if explicit:
        p = Path(explicit).expanduser().resolve()
        guard_not_final_test(p)
        if not p.exists():
            raise FileNotFoundError(p)
        return p
    hit = find_file(development_root.parent, ["data.yaml", "dataset.yaml"])
    if not hit:
        raise FileNotFoundError("YOLO data.yaml not found. Pass --data-yaml explicitly.")
    guard_not_final_test(hit)
    return hit


def discover_coco_json(development_root: Path, split: str, explicit: Optional[str]) -> Path:
    if explicit:
        p = Path(explicit).expanduser().resolve()
        guard_not_final_test(p)
        if not p.exists():
            raise FileNotFoundError(p)
        return p
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



MODEL_NAME = "BPD-YOLOn/L-FPN"
MODEL_SLUG = "bpd_yolon_lfpn"
MODEL_ROLE = "Tiny-object-specialized UAV baseline selected in Step 1"
BASE_PRETRAINED_DEFAULT = "yolov8n.pt"
ARTICLE_URL = "https://www.nature.com/articles/s41598-025-16878-6"
DYSAMPLE_REFERENCE_URL = "https://github.com/tiny-smart/dysample"

BPD_PROJECT_YAML = r"""
# Paper-faithful PROJECT REIMPLEMENTATION of BPD-YOLOn/L-FPN for Step 3.
# Important: the Scientific Reports paper describes the architecture but does not
# publish an official BPD-YOLO source-code repository in its Data Availability section.
# This YAML therefore MUST be reported as a project reimplementation, not author code.
#
# Paper-aligned elements represented here:
# - YOLOv8n-style lightweight backbone.
# - Original terminal SPPF removed.
# - P2-centric high-resolution detection path.
# - L-FPN-like dual-phase progressive fusion.
# - DSPF-style blocks realized explicitly with depthwise dilated convolutions r=1,2,3.
# - DySample-style content-aware point-sampling upsampling operator.
# - One target class: person.
#
# The baseline uses a single high-resolution P2 detection output to emphasize tiny objects.
# Keep this architecture frozen during the controlled baseline; architecture ablations
# belong in separately named runs.

nc: 1
depth_multiple: 1.0
width_multiple: 1.0

backbone:
  # [from, repeats, module, args]
  - [-1, 1, Conv, [16, 3, 2]]       # 0  P1/2
  - [-1, 1, Conv, [32, 3, 2]]       # 1  P2/4
  - [-1, 1, C2f, [32, True]]        # 2  C2
  - [-1, 1, Conv, [64, 3, 2]]       # 3  P3/8
  - [-1, 2, C2f, [64, True]]        # 4  C3
  - [-1, 1, Conv, [128, 3, 2]]      # 5  P4/16
  - [-1, 2, C2f, [128, True]]       # 6  C4
  - [-1, 1, Conv, [256, 3, 2]]      # 7  P5/32
  - [-1, 1, C2f, [256, True]]       # 8  C5 (no original SPPF)

head:
  # --- DAFF phase 1: down(C2) + C3 -> DSPF-like L1^3 -------------------------
  - [2, 1, Conv, [64, 3, 2]]        # 9  down C2 to P3
  - [[9, 4], 1, Concat, [1]]        # 10
  - [-1, 1, Conv, [64, 1, 1]]       # 11 base
  - [-1, 1, Conv, [64, 3, 1, null, 64, 1]]  # 12 dw dilated r1
  - [-1, 1, Conv, [64, 3, 1, null, 64, 2]]  # 13 dw dilated r2
  - [-1, 1, Conv, [64, 3, 1, null, 64, 3]]  # 14 dw dilated r3
  - [[11, 12, 13, 14], 1, Concat, [1]]       # 15
  - [-1, 1, Conv, [64, 1, 1]]       # 16 L1^3

  # --- DAFF phase 1: C4 + up(C5) -> DSPF-like L1^4 --------------------------
  - [8, 1, Conv, [128, 1, 1]]       # 17
  - [-1, 1, DySample, [2]]          # 18 up C5 P5->P4
  - [[6, 18], 1, Concat, [1]]       # 19
  - [-1, 1, Conv, [128, 1, 1]]      # 20 base
  - [-1, 1, Conv, [128, 3, 1, null, 128, 1]] # 21
  - [-1, 1, Conv, [128, 3, 1, null, 128, 2]] # 22
  - [-1, 1, Conv, [128, 3, 1, null, 128, 3]] # 23
  - [[20, 21, 22, 23], 1, Concat, [1]]       # 24
  - [-1, 1, Conv, [128, 1, 1]]      # 25 L1^4

  # --- DAFF phase 2: up(L1^4) + L1^3 -> L2^3 -------------------------------
  - [25, 1, Conv, [64, 1, 1]]       # 26
  - [-1, 1, DySample, [2]]          # 27
  - [[16, 27], 1, Concat, [1]]      # 28
  - [-1, 1, Conv, [64, 1, 1]]       # 29
  - [-1, 1, Conv, [64, 3, 1, null, 64, 1]]   # 30
  - [-1, 1, Conv, [64, 3, 1, null, 64, 2]]   # 31
  - [-1, 1, Conv, [64, 3, 1, null, 64, 3]]   # 32
  - [[29, 30, 31, 32], 1, Concat, [1]]       # 33
  - [-1, 1, Conv, [64, 1, 1]]       # 34 L2^3

  # --- DEI/deep semantic injection: up(C5) + L2^3 -> L3^3 -------------------
  - [8, 1, Conv, [64, 1, 1]]        # 35
  - [-1, 1, DySample, [4]]          # 36 P5->P3
  - [[34, 36], 1, Concat, [1]]      # 37
  - [-1, 1, Conv, [64, 1, 1]]       # 38
  - [-1, 1, Conv, [64, 3, 1, null, 64, 1]]   # 39
  - [-1, 1, Conv, [64, 3, 1, null, 64, 2]]   # 40
  - [-1, 1, Conv, [64, 3, 1, null, 64, 3]]   # 41
  - [[38, 39, 40, 41], 1, Concat, [1]]       # 42
  - [-1, 1, Conv, [64, 1, 1]]       # 43 L3^3

  # --- Progressive high-resolution P2 fusion -------------------------------
  - [16, 1, Conv, [32, 1, 1]]       # 44
  - [-1, 1, DySample, [2]]          # 45 L1^2
  - [34, 1, Conv, [32, 1, 1]]       # 46
  - [-1, 1, DySample, [2]]          # 47
  - [[45, 47, 2], 1, Concat, [1]]   # 48 + shallow C2
  - [-1, 1, C2f, [32, True]]        # 49 L2^2
  - [43, 1, Conv, [32, 1, 1]]       # 50
  - [-1, 1, DySample, [2]]          # 51
  - [[45, 49, 51, 2], 1, Concat, [1]] # 52 dense P2 fusion
  - [-1, 2, C2f, [64, True]]        # 53 feature extraction
  - [-1, 1, Conv, [64, 3, 1]]       # 54 final P2 feature
  - [[54], 1, Detect, [nc]]          # 55 person detector
"""


try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F

    class DySample(nn.Module):
        """
        Compact project implementation of content-aware point-sampling upsampling.

        It follows the DySample principle used by BPD-YOLO:
          - predict content-dependent sampling offsets,
          - add offsets to a regular sampling grid,
          - use torch.grid_sample to obtain the upsampled feature.

        This implementation is written for this project; it is not copied from the
        DySample authors' source and must not be described as bit-for-bit author code.
        """

        def __init__(self, scale: int = 2, max_offset: float = 0.25):
            super().__init__()
            self.scale = int(scale)
            self.max_offset = float(max_offset)
            self.offset = nn.LazyConv2d(2, kernel_size=1, stride=1, padding=0)
            self._zero_initialized = False

        def _init_offset(self, x):
            if not self._zero_initialized:
                _ = self.offset(x)  # materialize LazyConv2d
                with torch.no_grad():
                    nn.init.zeros_(self.offset.weight)
                    if self.offset.bias is not None:
                        nn.init.zeros_(self.offset.bias)
                self._zero_initialized = True

        def forward(self, x):
            self._init_offset(x)
            b, c, h, w = x.shape
            oh, ow = h * self.scale, w * self.scale

            raw = self.offset(x)
            raw = F.interpolate(raw, size=(oh, ow), mode="bilinear", align_corners=False)
            raw = torch.tanh(raw) * self.max_offset

            ys = (torch.arange(oh, device=x.device, dtype=x.dtype) + 0.5) / oh * 2.0 - 1.0
            xs = (torch.arange(ow, device=x.device, dtype=x.dtype) + 0.5) / ow * 2.0 - 1.0
            yy, xx = torch.meshgrid(ys, xs, indexing="ij")
            base = torch.stack((xx, yy), dim=-1).unsqueeze(0).expand(b, -1, -1, -1)

            dx = raw[:, 0] * (2.0 / max(w, 1))
            dy = raw[:, 1] * (2.0 / max(h, 1))
            grid = base + torch.stack((dx, dy), dim=-1)
            return F.grid_sample(
                x, grid, mode="bilinear", padding_mode="border", align_corners=False
            )

except Exception:
    DySample = None  # dependency check in main() will provide a clear error


def write_bpd_yaml(path: Path) -> None:
    ensure_dir(path.parent)
    path.write_text(BPD_PROJECT_YAML.strip() + "\n", encoding="utf-8")


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


def export_ultralytics_predictions_to_coco_bpd(
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
        )
        if results:
            boxes = getattr(results[0], "boxes", None)
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
            print(f"[BPD COCO export] {idx}/{len(ordered_images)} internal-val images", flush=True)

    write_json(out_json, predictions)
    return predictions, image_paths


def main() -> None:
    parser = make_base_parser(
        "Train the Step-3 BPD-YOLOn/L-FPN tiny-object baseline and archive all report-required artifacts."
    )
    parser.add_argument("--data-yaml", type=str, default=None)
    parser.add_argument("--coco-val", type=str, default=None)
    parser.add_argument("--base-pretrained", type=str, default=BASE_PRETRAINED_DEFAULT,
                        help="YOLOv8n checkpoint used for compatible backbone transfer.")
    parser.add_argument("--external-model-yaml", type=str, default=None,
                        help="Optional exact author/repository model YAML if obtained later. "
                             "When omitted, the embedded paper-faithful project reimplementation is used.")
    parser.add_argument("--optimizer", type=str, default="SGD")
    parser.add_argument("--lr0", type=float, default=0.01,
                        help="Paper reports initial LR=0.01 for BPD-YOLO.")
    parser.add_argument("--lrf", type=float, default=0.01,
                        help="Cosine final LR factor: 0.01 -> final LR ~0.0001 from 0.01.")
    parser.add_argument("--momentum", type=float, default=0.937)
    parser.add_argument("--weight-decay", type=float, default=5e-4)
    parser.add_argument("--cos-lr", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--amp", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--deterministic", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--mosaic", type=float, default=0.50,
                        help="Paper uses Mosaic but does not publish a probability; this is a conservative project baseline.")
    parser.add_argument("--mixup", type=float, default=0.10,
                        help="Paper uses MixUp but does not publish a probability; record/ablate this project value.")
    parser.add_argument("--close-mosaic", type=int, default=10,
                        help="Paper disables data augmentation in its last 10 epochs.")
    parser.add_argument("--degrees", type=float, default=5.0)
    parser.add_argument("--translate", type=float, default=0.08)
    parser.add_argument("--scale", type=float, default=0.35)
    parser.add_argument("--fliplr", type=float, default=0.50)
    parser.add_argument("--flipud", type=float, default=0.0)
    parser.add_argument("--native-paper-budget", action="store_true",
                        help="Switch to the paper's 300-epoch optimization budget. "
                             "Do NOT mix this run into the fixed-45-epoch controlled comparison.")
    parser.add_argument("--save-period", type=int, default=1, help="Save an Ultralytics checkpoint after every epoch to Google Drive.")
    parser.add_argument("--resume", type=str, default="auto", help="auto = resume from this run's Drive last.pt when available; none = start fresh; or provide an explicit checkpoint path.")
    args = parser.parse_args()

    if args.native_paper_budget:
        args.epochs = 300

    mount_google_drive_if_requested(args.mount_drive)
    project_root = Path(args.project_root).expanduser().resolve() if args.project_root else discover_project_root()
    development_root = discover_development_root(project_root, args.development_root)
    manifest = discover_manifest(development_root, args.manifest)
    data_yaml = discover_data_yaml(development_root, args.data_yaml)
    coco_val = discover_coco_json(development_root, "val", args.coco_val)
    guard_not_final_test(development_root, manifest, data_yaml, coco_val)
    freeze = require_frozen_final_test(project_root, args.allow_missing_final_test_freeze)

    rows = load_manifest_rows(manifest)
    manifest_audit = audit_manifest(rows)
    assert_manifest_safe(manifest_audit, args.allow_missing_group_key)

    coco_val_data = load_coco_json(coco_val)
    validate_person_only_coco(coco_val_data)

    print_preflight_summary(MODEL_NAME, development_root, manifest, freeze, manifest_audit)
    if args.dry_run:
        print("Dry run complete. No training was started.")
        return

    ensure_dependencies([
        ("torch", "torch"),
        ("ultralytics", "ultralytics>=8.4.114"),
        ("pycocotools", "pycocotools"),
        ("PIL", "pillow"),
        ("numpy", "numpy"),
        ("matplotlib", "matplotlib"),
    ])

    import torch
    import ultralytics.nn.tasks as ultralytics_tasks
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

    # Register the project DySample operator so Ultralytics YAML parsing can resolve it.
    if DySample is None:
        raise RuntimeError("PyTorch is required before constructing BPD-YOLOn/L-FPN.")
    setattr(ultralytics_tasks, "DySample", DySample)

    if args.external_model_yaml:
        model_yaml = Path(args.external_model_yaml).expanduser().resolve()
        guard_not_final_test(model_yaml)
        if not model_yaml.exists():
            raise FileNotFoundError(model_yaml)
        implementation_status = "external architecture file supplied by user"
        safe_copy(model_yaml, sub["config"] / model_yaml.name)
    else:
        model_yaml = sub["config"] / "bpd_yolon_lfpn_project_reimplementation.yaml"
        write_bpd_yaml(model_yaml)
        implementation_status = (
            "paper-faithful project reimplementation; not official author source code"
        )

    protocol_name = (
        "bpd_paper_native_300epoch_budget"
        if args.native_paper_budget
        else "step3_fixed_budget_baseline"
    )
    protocol = {
        "name": protocol_name,
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
        "momentum": args.momentum,
        "weight_decay": args.weight_decay,
        "lr_schedule": "cosine",
        "augmentation": {
            "mosaic": args.mosaic,
            "mixup": args.mixup,
            "fliplr": args.fliplr,
            "flipud": args.flipud,
            "degrees": args.degrees,
            "translate": args.translate,
            "scale": args.scale,
            "close_mosaic_last_epochs": args.close_mosaic,
        },
        "paper_training_context": {
            "paper_visdrone_epochs": 300,
            "paper_visdrone_batch": 8,
            "paper_optimizer": "SGD",
            "paper_initial_lr": 0.01,
            "paper_final_lr": 0.0001,
            "paper_augmentations_named": ["Mosaic", "MixUp", "flipping"],
            "paper_augmentation_disabled_last_epochs": 10,
            "paper_tinyperson_imgsz": 1024,
            "paper_tinyperson_batch": 2,
        },
        "fairness_note": (
            "Unless --native-paper-budget is set, the project fixed 45-epoch / 1280 protocol takes precedence "
            "for cross-model comparison. Paper-reported probabilities for Mosaic/MixUp are not available, "
            "so project probabilities are explicitly recorded and must be ablated separately."
        ),
        "final_test_used": False,
        "private_final_test_required_for_step3": False,
        "checkpoint_policy": "save every completed epoch to persistent Google Drive storage",
        "default_colab_output_root": str(default_drive_output_root(project_root)),
        "requested_training_hardware": "Google Colab NVIDIA L4 GPU",
    }
    write_json(sub["config"] / "resolved_protocol.json", protocol)

    model_meta = {
        "name": MODEL_NAME,
        "slug": MODEL_SLUG,
        "role": MODEL_ROLE,
        "base_pretrained": args.base_pretrained,
        "article_url": ARTICLE_URL,
        "dysample_reference_url": DYSAMPLE_REFERENCE_URL,
        "implementation_status": implementation_status,
        "architecture_file": str(model_yaml),
        "architecture_file_sha256": sha256_file(model_yaml),
        "paper_aligned_components": [
            "YOLOv8n-family lightweight backbone",
            "terminal SPPF removed",
            "L-FPN high-resolution information flow",
            "DAFF-like progressive shallow/deep feature fusion",
            "DSPF-style depthwise separable dilated convolutions with dilation 1/2/3",
            "DySample-style content-aware point-sampling upsampling",
            "P2-centric small-object detection",
        ],
        "critical_reporting_note": (
            "The Scientific Reports article exposes data availability but no official BPD-YOLO source-code link. "
            "When the embedded architecture is used, Step 3 must call it a project reimplementation."
        ),
    }
    write_json(sub["config"] / "model_metadata.json", model_meta)

    resume_path = resolve_resume_checkpoint(run_root, args.resume, ultralytics_layout=True)
    if resume_path is not None:
        print(f"Resuming BPD-YOLOn/L-FPN training from Google Drive checkpoint: {resume_path}")
        # Register the custom operator before loading the custom checkpoint.
        setattr(ultralytics_tasks, "DySample", DySample)
        model = YOLO(str(resume_path), task="detect")
        append_jsonl(
            sub["audit"] / "resume_history.jsonl",
            {"utc": utc_now(), "mode": "resume", "checkpoint": str(resume_path)},
        )
    else:
        print("Building BPD-YOLOn/L-FPN architecture:", model_yaml)
        model = YOLO(str(model_yaml), task="detect")
        # Transfer compatible backbone weights from YOLOv8n. Ultralytics loads only shape-compatible keys.
        if args.base_pretrained:
            print("Transferring compatible weights from:", args.base_pretrained)
            model.load(args.base_pretrained)
        append_jsonl(
            sub["audit"] / "resume_history.jsonl",
            {"utc": utc_now(), "mode": "fresh", "checkpoint": args.base_pretrained},
        )

    train_kwargs: Dict[str, Any] = dict(
        data=str(data_yaml),
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
        lr0=args.lr0,
        lrf=args.lrf,
        momentum=args.momentum,
        weight_decay=args.weight_decay,
        cos_lr=args.cos_lr,
        mosaic=args.mosaic,
        mixup=args.mixup,
        close_mosaic=args.close_mosaic,
        degrees=args.degrees,
        translate=args.translate,
        scale=args.scale,
        fliplr=args.fliplr,
        flipud=args.flipud,
        perspective=0.0,
        shear=0.0,
        copy_paste=0.0,
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
    if resume_path is not None:
        train_kwargs["resume"] = str(resume_path)

    write_json(sub["config"] / "train_kwargs.json", train_kwargs)

    # Fingerprint the executable implementation used for scientific traceability.
    script_path = Path(__file__).resolve()
    write_json(
        sub["audit"] / "implementation_fingerprint.json",
        {
            "script": str(script_path),
            "script_sha256": sha256_file(script_path),
            "model_yaml": str(model_yaml),
            "model_yaml_sha256": sha256_file(model_yaml),
            "implementation_status": implementation_status,
        },
    )

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

    # Re-register custom operator before loading custom checkpoint in a fresh YOLO object.
    setattr(ultralytics_tasks, "DySample", DySample)
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
    predictions, image_paths = export_ultralytics_predictions_to_coco_bpd(
        eval_model, coco_val, development_root, args.imgsz, device, args.max_det, pred_json
    )
    standardized = coco_eval_metrics(coco_val, pred_json, max_dets=args.max_det)
    operating = threshold_operating_metrics(
        coco_val_data, predictions, args.operating_conf, args.operating_iou
    )
    write_json(sub["metrics"] / "standardized_coco_metrics.json", standardized)
    write_json(sub["metrics"] / "operating_point_metrics.json", operating)
    save_operating_metrics_csv(sub["metrics"] / "failure_ranking.csv", operating)
    save_failure_visuals(
        coco_val_data, predictions, image_paths, operating, sub["failures"],
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

    first_iid = int(coco_val_data["images"][0]["id"])
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
            "fixed_budget_completed": not args.native_paper_budget,
            "paper_native_budget_run": args.native_paper_budget,
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
            "paper_reference_bpd_yolon": {
                "parameters_million": 1.50,
                "gflops_reference_protocol": 11.4,
                "note": "Reference paper values; do not substitute for profiling this project reimplementation.",
            },
            "project_flops": "Profile this exact checkpoint/input with framework profiler before reporting.",
        },
        "artifacts": {
            "best_checkpoint": best_rec,
            "last_checkpoint": last_rec,
            "best_checkpoint_sha256": best_rec.get("sha256"),
            "last_checkpoint_sha256": last_rec.get("sha256"),
            "architecture_file": str(model_yaml),
            "architecture_file_sha256": sha256_file(model_yaml),
            "predictions_json": str(pred_json),
            "standardized_metrics_json": str(sub["metrics"] / "standardized_coco_metrics.json"),
            "failure_ranking_csv": str(sub["metrics"] / "failure_ranking.csv"),
        },
        "scientific_notes": [
            "The paper's exact public BPD-YOLO training source was not identified in the article's Data Availability section.",
            "When using the embedded architecture, report this run as a paper-faithful project reimplementation, not official author code.",
            "DSPF dilation rates 1/2/3, depthwise separable dilated convolution, DySample principle, high-resolution L-FPN flow, and YOLOv8n-family base follow the paper description.",
            "The frozen private Final Test is not read in Step 3.",
            "TensorRT deployment benchmarking belongs to Step 4.",
        ],
    }
    write_json(run_root / "STEP3_RUN_REPORT.json", report)
    write_markdown_report(run_root / "STEP3_RUN_REPORT.md", report)

    print("\nTraining complete.")
    print("Run directory:", run_root)
    print("Implementation status:", implementation_status)
    print("Best epoch:", best_epoch)
    print("Primary internal-val mAP50-95:", metrics["map50_95"])
    print("Primary internal-val AP50:", metrics["ap50"])
    print("Internal-val Recall@operating-point:", metrics["recall"])
    print("Peak VRAM MB:", peak_mb)
    print("Warm median latency ms:", latency.get("warm_latency_median_ms"))
    print("Best checkpoint:", best_copy)
    print("Private Final Test content accessed: NO (presence is optional in Step 3)")


if __name__ == "__main__":
    main()
