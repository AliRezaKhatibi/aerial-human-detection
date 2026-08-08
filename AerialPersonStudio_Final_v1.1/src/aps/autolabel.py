from __future__ import annotations
from pathlib import Path
from typing import Callable
import math

import numpy as np

from .config import AutoLabelConfig
from .dataset import StudioDataset

PERSON_NAMES = {"person", "pedestrian", "people", "human"}


def _iou(a, b):
    ax1, ay1, ax2, ay2 = a[:4]
    bx1, by1, bx2, by2 = b[:4]
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    aa = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    ba = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    den = aa + ba - inter
    return inter / den if den > 0 else 0.0


def nms(boxes, iou_threshold=0.55):
    boxes = sorted(boxes, key=lambda b: b[4], reverse=True)
    keep = []
    while boxes:
        best = boxes.pop(0)
        keep.append(best)
        boxes = [b for b in boxes if _iou(best, b) < iou_threshold]
    return keep


def _model_person_ids(model):
    names = model.names if isinstance(model.names, dict) else {i: n for i, n in enumerate(model.names)}
    names = {int(k): str(v) for k, v in names.items()}
    if len(names) == 1:
        return [next(iter(names))], names
    ids = [i for i, n in names.items() if n.strip().lower() in PERSON_NAMES]
    if not ids:
        raise RuntimeError(f"No person-like class found in model: {names}")
    return ids, names


def _device_value(requested: str):
    if requested.lower() != "auto":
        return requested
    import torch
    return 0 if torch.cuda.is_available() else "cpu"


def _result_boxes(result, ox=0, oy=0):
    out = []
    if result.boxes is None or len(result.boxes) == 0:
        return out
    xyxy = result.boxes.xyxy.cpu().tolist()
    confs = result.boxes.conf.cpu().tolist()
    for b, c in zip(xyxy, confs):
        x1, y1, x2, y2 = map(float, b)
        out.append([x1 + ox, y1 + oy, x2 + ox, y2 + oy, float(c)])
    return out


def _infer_full(model, path: Path, cfg: AutoLabelConfig, class_ids, device):
    r = model.predict(
        source=str(path), imgsz=cfg.imgsz, conf=cfg.confidence, iou=cfg.iou,
        max_det=cfg.max_det, classes=class_ids, device=device, verbose=False,
    )[0]
    return _result_boxes(r)


def _infer_tiled(model, path: Path, cfg: AutoLabelConfig, class_ids, device):
    import cv2
    img = cv2.imread(str(path))
    if img is None:
        raise RuntimeError(f"Unreadable image: {path}")
    h, w = img.shape[:2]
    tile = max(256, int(cfg.tile_size))
    stride = max(64, int(tile * (1.0 - cfg.tile_overlap)))
    xs = list(range(0, max(1, w - tile + 1), stride))
    ys = list(range(0, max(1, h - tile + 1), stride))
    if not xs or xs[-1] + tile < w:
        xs.append(max(0, w - tile))
    if not ys or ys[-1] + tile < h:
        ys.append(max(0, h - tile))
    xs, ys = sorted(set(xs)), sorted(set(ys))

    all_boxes = []
    # include full-frame pass to preserve context
    all_boxes.extend(_infer_full(model, path, cfg, class_ids, device))
    for y in ys:
        for x in xs:
            crop = img[y:min(h, y + tile), x:min(w, x + tile)]
            r = model.predict(
                source=crop, imgsz=cfg.imgsz, conf=cfg.confidence, iou=cfg.iou,
                max_det=cfg.max_det, classes=class_ids, device=device, verbose=False,
            )[0]
            all_boxes.extend(_result_boxes(r, x, y))
    return nms(all_boxes, iou_threshold=min(0.65, max(0.35, cfg.iou)))


def run_autolabel(
    workspace: Path,
    split: str,
    cfg: AutoLabelConfig,
    progress: Callable[[int, int, str], None] | None = None,
    log: Callable[[str], None] | None = None,
    overwrite: bool = True,
):
    from ultralytics import YOLO

    ds = StudioDataset(workspace)
    records = ds.records(split)
    if not records:
        raise RuntimeError(f"No editable Studio images for split '{split}'. Import prepared ZIPs or run Prepare first.")

    model_path = Path(cfg.model_path)
    if not model_path.is_absolute():
        # first resolve relative to application CWD, then workspace
        if model_path.exists():
            model_path = model_path.resolve()
        else:
            model_path = (Path(workspace) / model_path).resolve()
    if not model_path.exists():
        raise FileNotFoundError(f"Model not found: {model_path}")

    model = YOLO(str(model_path))
    class_ids, names = _model_person_ids(model)
    device = _device_value(cfg.device)
    if log:
        log(f"Loaded model: {model_path.name}")
        log(f"Model classes: {names}; selected IDs: {class_ids}; canonical output: person")
        log(f"Device: {device}; conf={cfg.confidence}; imgsz={cfg.imgsz}; tiled={cfg.tiled_inference}")

    for idx, rec in enumerate(records, start=1):
        path = ds.image_path(rec)
        raw = _infer_tiled(model, path, cfg, class_ids, device) if cfg.tiled_inference else _infer_full(model, path, cfg, class_ids, device)
        boxes = []
        for x1, y1, x2, y2, conf in raw:
            x1 = max(0.0, min(float(rec["width"]), x1))
            y1 = max(0.0, min(float(rec["height"]), y1))
            x2 = max(0.0, min(float(rec["width"]), x2))
            y2 = max(0.0, min(float(rec["height"]), y2))
            if x2 - x1 < 1 or y2 - y1 < 1:
                continue
            boxes.append({
                "x1": x1, "y1": y1, "x2": x2, "y2": y2,
                "label": "person", "confidence": round(float(conf), 6), "source": "model",
            })
        if overwrite or not ds.boxes(split, rec["name"]):
            ds.annotations[ds.key(split, rec["name"])] = boxes
        else:
            ds.annotations.setdefault(ds.key(split, rec["name"]), []).extend(boxes)
        if progress:
            progress(idx, len(records), rec["name"])
    ds.save()
    return ds.stats()[split]
