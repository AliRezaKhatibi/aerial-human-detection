"""YOLO26s-P2 final Colab training pipeline."""

# آموزش نهایی YOLO26s-P2 برای تشخیص انسان در تصاویر هوایی
# Install before running:
# pip install ultralytics==8.4.114 onnx onnxslim onnxruntime-gpu pyyaml pandas tqdm

# ============================================================
# CELL 2 — Imports, Google Drive and environment report
# ============================================================

from __future__ import annotations

from pathlib import Path
from datetime import datetime
from collections import Counter, defaultdict
from typing import Any, Iterable
import gc
import hashlib
import json
import platform
import shutil
import subprocess
import sys
import warnings

import cv2
import numpy as np
import pandas as pd
import torch
import yaml
from tqdm.auto import tqdm
from IPython.display import display

import ultralytics
from ultralytics import YOLO

from google.colab import drive
drive.mount("/content/drive")

print("=" * 100)
print("ENVIRONMENT")
print("=" * 100)
print("Python:", sys.version.replace("\n", " "))
print("Ultralytics:", ultralytics.__version__)
print("PyTorch:", torch.__version__)
print("CUDA available:", torch.cuda.is_available())
print("CUDA runtime:", torch.version.cuda)

if not torch.cuda.is_available():
    raise RuntimeError("Enable a GPU runtime in Colab before training.")

GPU_INDEX = 0
GPU_NAME = torch.cuda.get_device_name(GPU_INDEX)
GPU_MEMORY_GB = torch.cuda.get_device_properties(GPU_INDEX).total_memory / 1024**3

print("GPU:", GPU_NAME)
print(f"GPU memory: {GPU_MEMORY_GB:.2f} GB")
subprocess.run(["nvidia-smi"], check=False)

assert ultralytics.__version__ == "8.4.114", (
    "Unexpected Ultralytics version. Restart the runtime and rerun CELL 1."
)

# ============================================================
# CELL 3 — Global configuration
# ============================================================

LOCAL_PROJECT_ROOT = Path("/content/aerial_person_final_product")
DRIVE_PROJECT_ROOT = Path(
    "/content/drive/MyDrive/aerial_person_yolo26s_p2_final"
)

CONFIG_DIR = DRIVE_PROJECT_ROOT / "configs"
RUNS_DIR = DRIVE_PROJECT_ROOT / "runs"
REPORTS_DIR = DRIVE_PROJECT_ROOT / "reports"
EXPORTS_DIR = DRIVE_PROJECT_ROOT / "exports"
FINAL_DIR = DRIVE_PROJECT_ROOT / "final_model"

for directory in (CONFIG_DIR, RUNS_DIR, REPORTS_DIR, EXPORTS_DIR, FINAL_DIR):
    directory.mkdir(parents=True, exist_ok=True)

FULL_DATA_CANDIDATES = [
    LOCAL_PROJECT_ROOT / "datasets/visdrone_person/data.yaml",
    LOCAL_PROJECT_ROOT / "datasets/visdrone_person_full/data.yaml",
]

HYBRID_DATA_CANDIDATES = [
    LOCAL_PROJECT_ROOT / "datasets/visdrone_person_context_tiles/data.yaml",
    LOCAL_PROJECT_ROOT / "datasets/visdrone_person_hybrid/data.yaml",
]

BASE_WEIGHTS = "yolo26s.pt"
SEED = 42
DEVICE = 0
WORKERS = 4
NBS = 64
MAX_DET = 1000
VAL_IOU = 0.70
TEST_CONF = 0.001
IMAGE_SIZE_FINAL = 1280

STAGE_1_EPOCHS = 8
STAGE_2_EPOCHS = 32
STAGE_3_EPOCHS = 10

FORCE_RESTART_STAGES = False
RUN_SIZE_DIAGNOSTIC = True
RUN_ONNX_EXPORT = True
RUN_ONNX_VALIDATION = True

# Optional baseline checkpoint. Leave as None to skip.
BASELINE_PT = None

print("Drive project root:", DRIVE_PROJECT_ROOT)

# ============================================================
# CELL 4 — Dataset discovery and validation
# ============================================================

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}


def first_existing(paths: Iterable[Path]) -> Path | None:
    for path in paths:
        if path.exists():
            return path.resolve()
    return None


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Invalid YAML dictionary: {path}")
    return data


def dataset_root_from_yaml(yaml_path: Path, config: dict[str, Any]) -> Path:
    root_value = config.get("path")
    if root_value is None:
        return yaml_path.parent.resolve()
    root = Path(str(root_value))
    return root if root.is_absolute() else (yaml_path.parent / root).resolve()


def resolve_split_entries(yaml_path: Path, split_name: str) -> list[Path]:
    config = load_yaml(yaml_path)
    root = dataset_root_from_yaml(yaml_path, config)
    value = config.get(split_name)
    if value is None:
        return []
    values = value if isinstance(value, list) else [value]
    output = []
    for item in values:
        path = Path(str(item))
        output.append(path if path.is_absolute() else (root / path).resolve())
    return output


def collect_images(entries: list[Path]) -> list[Path]:
    images = []
    for entry in entries:
        if entry.is_file() and entry.suffix.lower() == ".txt":
            for line in entry.read_text(encoding="utf-8").splitlines():
                candidate = Path(line.strip())
                if not candidate.is_absolute():
                    candidate = (entry.parent / candidate).resolve()
                if candidate.suffix.lower() in IMAGE_SUFFIXES:
                    images.append(candidate)
        elif entry.is_file() and entry.suffix.lower() in IMAGE_SUFFIXES:
            images.append(entry)
        elif entry.is_dir():
            images.extend(
                path for path in entry.rglob("*")
                if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
            )
    return sorted(set(images))


def image_to_label_path(image_path: Path) -> Path:
    parts = list(image_path.parts)
    for index in range(len(parts) - 1, -1, -1):
        if parts[index] == "images":
            parts[index] = "labels"
            return Path(*parts).with_suffix(".txt")
    return image_path.with_suffix(".txt")


def inspect_dataset(yaml_path: Path, title: str) -> dict[str, Any]:
    config = load_yaml(yaml_path)
    required = ("train", "val", "test")
    missing = [key for key in required if not config.get(key)]
    if missing:
        raise ValueError(f"{title} is missing splits {missing}: {yaml_path}")

    nc = int(config.get("nc", len(config.get("names", []))))
    if nc != 1:
        warnings.warn(
            f"{title} reports nc={nc}. Verify that this is the intended Person-only dataset."
        )

    result = {
        "title": title,
        "yaml": str(yaml_path),
        "nc": nc,
        "names": config.get("names"),
    }

    for split in required:
        images = [
            path for path in collect_images(resolve_split_entries(yaml_path, split))
            if path.exists()
        ]
        if not images:
            raise FileNotFoundError(
                f"No images were found for split '{split}' in {yaml_path}"
            )
        labels = [image_to_label_path(path) for path in images]
        result[f"{split}_images"] = len(images)
        result[f"{split}_labels"] = sum(path.exists() for path in labels)
        result[f"{split}_backgrounds"] = sum(
            (not path.exists()) or path.stat().st_size == 0 for path in labels
        )
    return result


FULL_DATA_YAML = first_existing(FULL_DATA_CANDIDATES)
HYBRID_DATA_YAML = first_existing(HYBRID_DATA_CANDIDATES)

if HYBRID_DATA_YAML is None:
    raise FileNotFoundError(
        "Hybrid/context data.yaml was not found:\n"
        + "\n".join(str(path) for path in HYBRID_DATA_CANDIDATES)
    )

if FULL_DATA_YAML is None:
    warnings.warn(
        "A separate full-scene data.yaml was not found. "
        "The hybrid data.yaml will be used in all stages."
    )
    FULL_DATA_YAML = HYBRID_DATA_YAML

dataset_summary_df = pd.DataFrame([
    inspect_dataset(FULL_DATA_YAML, "Full-scene dataset"),
    inspect_dataset(HYBRID_DATA_YAML, "Hybrid/context dataset"),
])
display(dataset_summary_df)

dataset_summary_path = REPORTS_DIR / "dataset_summary.csv"
dataset_summary_df.to_csv(dataset_summary_path, index=False)

print("Full data YAML:", FULL_DATA_YAML)
print("Hybrid data YAML:", HYBRID_DATA_YAML)

# ============================================================
# CELL 5 — Conservative automatic batch selection
# ============================================================

def choose_batches(memory_gb: float) -> dict[str, int]:
    if memory_gb >= 20:
        return {"stage1": 8, "stage2": 4, "stage3": 4, "val": 4}
    if memory_gb >= 14:
        return {"stage1": 4, "stage2": 2, "stage3": 2, "val": 2}
    if memory_gb >= 8:
        return {"stage1": 2, "stage2": 1, "stage3": 1, "val": 1}
    return {"stage1": 1, "stage2": 1, "stage3": 1, "val": 1}


BATCHES = choose_batches(GPU_MEMORY_GB)
print(json.dumps(BATCHES, indent=2))

# ============================================================
# CELL 6 — Prepare official YOLO26s-P2 and transfer report
# ============================================================

PACKAGE_ROOT = Path(ultralytics.__file__).resolve().parent
OFFICIAL_P2_YAML = PACKAGE_ROOT / "cfg/models/26/yolo26-p2.yaml"

if not OFFICIAL_P2_YAML.exists():
    raise FileNotFoundError(
        f"Official yolo26-p2.yaml was not found: {OFFICIAL_P2_YAML}"
    )

P2_YAML = CONFIG_DIR / "yolo26s-p2.yaml"
p2_config = load_yaml(OFFICIAL_P2_YAML)
p2_config["nc"] = 1

with P2_YAML.open("w", encoding="utf-8") as handle:
    yaml.safe_dump(p2_config, handle, sort_keys=False, allow_unicode=True)

base_model = YOLO(BASE_WEIGHTS)
fresh_p2_model = YOLO(str(P2_YAML))

base_state = base_model.model.state_dict()
p2_state = fresh_p2_model.model.state_dict()

compatible_keys = [
    key for key, value in p2_state.items()
    if key in base_state and tuple(value.shape) == tuple(base_state[key].shape)
]
compatible_numel = sum(p2_state[key].numel() for key in compatible_keys)
total_numel = sum(value.numel() for value in p2_state.values())

transfer_report = {
    "base_weights": BASE_WEIGHTS,
    "p2_yaml": str(P2_YAML),
    "compatible_tensor_keys": len(compatible_keys),
    "total_p2_tensor_keys": len(p2_state),
    "compatible_numel": int(compatible_numel),
    "total_p2_numel": int(total_numel),
    "compatible_numel_ratio": float(compatible_numel / total_numel),
}

transfer_report_path = REPORTS_DIR / "pretrained_transfer_report.json"
transfer_report_path.write_text(
    json.dumps(transfer_report, indent=2, ensure_ascii=False),
    encoding="utf-8",
)

print(json.dumps(transfer_report, indent=2))
fresh_p2_model.info(detailed=False, verbose=True)

del base_model, fresh_p2_model
gc.collect()
torch.cuda.empty_cache()

# ============================================================
# CELL 7 — Safe training and resume utilities
# ============================================================

def clear_memory() -> None:
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


def count_completed_epochs(results_csv: Path) -> int:
    if not results_csv.exists():
        return 0
    try:
        return len(pd.read_csv(results_csv))
    except Exception:
        return 0


def stage_paths(stage_name: str) -> dict[str, Path]:
    run_dir = RUNS_DIR / stage_name
    return {
        "run_dir": run_dir,
        "last": run_dir / "weights/last.pt",
        "best": run_dir / "weights/best.pt",
        "results": run_dir / "results.csv",
    }


def run_or_resume_stage(
    *,
    stage_name: str,
    source: str | Path,
    epochs: int,
    data_yaml: Path,
    train_args: dict[str, Any],
    build_p2_from_base: bool = False,
) -> Path:
    paths = stage_paths(stage_name)

    if FORCE_RESTART_STAGES and paths["run_dir"].exists():
        shutil.rmtree(paths["run_dir"])

    completed = count_completed_epochs(paths["results"])

    print("\n" + "=" * 110)
    print("STAGE:", stage_name)
    print("Expected epochs:", epochs)
    print("Completed rows:", completed)
    print("Data:", data_yaml)
    print("=" * 110)

    if paths["best"].exists() and paths["last"].exists() and completed >= epochs:
        print("Stage already complete. Reusing best.pt.")
        return paths["best"]

    clear_memory()

    if paths["last"].exists() and completed > 0:
        print("Incomplete stage detected. Resuming last.pt.")
        model = YOLO(str(paths["last"]))
        model.train(resume=True)
    else:
        print("Starting new stage from:", source)
        model = (
            YOLO(str(P2_YAML)).load(str(source))
            if build_p2_from_base
            else YOLO(str(source))
        )
        model.train(
            data=str(data_yaml),
            epochs=epochs,
            project=str(RUNS_DIR),
            name=stage_name,
            exist_ok=True,
            **train_args,
        )

    paths = stage_paths(stage_name)
    selected = paths["best"] if paths["best"].exists() else paths["last"]

    if not selected.exists():
        raise FileNotFoundError(f"No checkpoint was produced for {stage_name}")

    del model
    clear_memory()
    print("Selected checkpoint:", selected)
    return selected


COMMON_ARGS = {
    "device": DEVICE,
    "workers": WORKERS,
    "single_cls": True,
    "optimizer": "AdamW",
    "amp": True,
    "cos_lr": True,
    "seed": SEED,
    "deterministic": True,
    "max_det": MAX_DET,
    "iou": VAL_IOU,
    "nbs": NBS,
    "weight_decay": 5e-4,
    "momentum": 0.937,
    "patience": 100,
    "save": True,
    "save_period": 5,
    "plots": True,
    "val": True,
    "verbose": True,
    "cache": False,
    "rect": False,
    "compile": False,
    "channels_last": False,
}

# ============================================================
# CELL 8 — Stage 1: P2 warm-up at 960
# ============================================================

stage1_args = {
    **COMMON_ARGS,
    "imgsz": 960,
    "batch": BATCHES["stage1"],
    "freeze": 10,
    "lr0": 2.0e-4,
    "lrf": 0.10,
    "warmup_epochs": 1.0,
    "warmup_momentum": 0.8,
    "warmup_bias_lr": 0.05,
    "mosaic": 1.0,
    "close_mosaic": 0,
    "mixup": 0.03,
    "copy_paste": 0.0,
    "cutmix": 0.0,
    "hsv_h": 0.015,
    "hsv_s": 0.50,
    "hsv_v": 0.35,
    "degrees": 5.0,
    "translate": 0.10,
    "scale": 0.45,
    "shear": 2.0,
    "perspective": 0.0002,
    "fliplr": 0.50,
    "flipud": 0.0,
    "erasing": 0.30,
    "auto_augment": "randaugment",
}

STAGE_1_BEST = run_or_resume_stage(
    stage_name="stage1_p2_warmup_960",
    source=BASE_WEIGHTS,
    epochs=STAGE_1_EPOCHS,
    data_yaml=FULL_DATA_YAML,
    train_args=stage1_args,
    build_p2_from_base=True,
)

print("Stage 1 best:", STAGE_1_BEST)

# ============================================================
# CELL 9 — Stage 2: Main hybrid training at 1280
# ============================================================

stage2_args = {
    **COMMON_ARGS,
    "imgsz": 1280,
    "batch": BATCHES["stage2"],
    "freeze": None,
    "lr0": 4.0e-4,
    "lrf": 0.05,
    "warmup_epochs": 1.0,
    "warmup_momentum": 0.8,
    "warmup_bias_lr": 0.05,
    "mosaic": 1.0,
    "close_mosaic": 0,
    "mixup": 0.03,
    "copy_paste": 0.0,
    "cutmix": 0.0,
    "hsv_h": 0.015,
    "hsv_s": 0.50,
    "hsv_v": 0.35,
    "degrees": 5.0,
    "translate": 0.10,
    "scale": 0.45,
    "shear": 2.0,
    "perspective": 0.0002,
    "fliplr": 0.50,
    "flipud": 0.0,
    "erasing": 0.40,
    "auto_augment": "randaugment",
}

STAGE_2_BEST = run_or_resume_stage(
    stage_name="stage2_hybrid_1280",
    source=STAGE_1_BEST,
    epochs=STAGE_2_EPOCHS,
    data_yaml=HYBRID_DATA_YAML,
    train_args=stage2_args,
)

print("Stage 2 best:", STAGE_2_BEST)

# Install before running:
# pip install ultralytics==8.4.114 onnx onnxslim onnxruntime-gpu pyyaml pandas tqdm

# Install before running:
# pip install ultralytics==8.4.114 onnx onnxslim onnxruntime-gpu pyyaml pandas tqdm

# Install before running:
# pip install ultralytics==8.4.114 onnx onnxslim onnxruntime-gpu pyyaml pandas tqdm

# Install before running:
# pip install ultralytics==8.4.114 onnx onnxslim onnxruntime-gpu pyyaml pandas tqdm

# Install before running:
# pip install ultralytics==8.4.114 onnx onnxslim onnxruntime-gpu pyyaml pandas tqdm

# Install before running:
# pip install ultralytics==8.4.114 onnx onnxslim onnxruntime-gpu pyyaml pandas tqdm

# Install before running:
# pip install ultralytics==8.4.114 onnx onnxslim onnxruntime-gpu pyyaml pandas tqdm

# Install before running:
# pip install ultralytics==8.4.114 onnx onnxslim onnxruntime-gpu pyyaml pandas tqdm

# ساخت TensorRT روی RTX 3070