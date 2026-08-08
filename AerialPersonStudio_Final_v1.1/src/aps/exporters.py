from __future__ import annotations
import csv
import json
import shutil
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

from .dataset import StudioDataset


def _reset_dir(path: Path):
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def export_yolo(workspace: Path):
    ds = StudioDataset(workspace)
    root = ds.paths.outputs / "yolo"
    _reset_dir(root)
    for split in ("train", "val", "test"):
        img_dir = root / "images" / split
        lab_dir = root / "labels" / split
        img_dir.mkdir(parents=True, exist_ok=True)
        lab_dir.mkdir(parents=True, exist_ok=True)
        for rec in ds.records(split):
            src = ds.image_path(rec)
            shutil.copy2(src, img_dir / rec["name"])
            w, h = float(rec["width"]), float(rec["height"])
            lines = []
            for b in ds.boxes(split, rec["name"]):
                x1, y1, x2, y2 = b["x1"], b["y1"], b["x2"], b["y2"]
                xc, yc = ((x1 + x2) / 2) / w, ((y1 + y2) / 2) / h
                bw, bh = (x2 - x1) / w, (y2 - y1) / h
                lines.append(f"0 {xc:.8f} {yc:.8f} {bw:.8f} {bh:.8f}")
            (lab_dir / f"{Path(rec['name']).stem}.txt").write_text(("\n".join(lines) + "\n") if lines else "", encoding="utf-8")
    (root / "data.yaml").write_text(
        "path: .\ntrain: images/train\nval: images/val\ntest: images/test\nnames:\n  0: person\n",
        encoding="utf-8",
    )
    return root


def export_visdrone(workspace: Path):
    ds = StudioDataset(workspace)
    root = ds.paths.outputs / "visdrone"
    _reset_dir(root)
    for split in ("train", "val", "test"):
        img_dir = root / split / "images"
        ann_dir = root / split / "annotations"
        img_dir.mkdir(parents=True, exist_ok=True)
        ann_dir.mkdir(parents=True, exist_ok=True)
        for rec in ds.records(split):
            shutil.copy2(ds.image_path(rec), img_dir / rec["name"])
            lines = []
            for b in ds.boxes(split, rec["name"]):
                left, top = b["x1"], b["y1"]
                bw, bh = b["x2"] - b["x1"], b["y2"] - b["y1"]
                lines.append(f"{left:.3f},{top:.3f},{bw:.3f},{bh:.3f},1,1,0,0")
            (ann_dir / f"{Path(rec['name']).stem}.txt").write_text(("\n".join(lines) + "\n") if lines else "", encoding="utf-8")
    return root


def export_coco(workspace: Path):
    ds = StudioDataset(workspace)
    root = ds.paths.outputs / "coco"
    _reset_dir(root)
    for split in ("train", "val", "test"):
        images, anns = [], []
        ann_id = 1
        for image_id, rec in enumerate(ds.records(split), start=1):
            images.append({"id": image_id, "file_name": rec["name"], "width": rec["width"], "height": rec["height"]})
            for b in ds.boxes(split, rec["name"]):
                bw, bh = b["x2"] - b["x1"], b["y2"] - b["y1"]
                anns.append({
                    "id": ann_id, "image_id": image_id, "category_id": 1,
                    "bbox": [b["x1"], b["y1"], bw, bh], "area": bw * bh, "iscrowd": 0,
                })
                ann_id += 1
        obj = {"images": images, "annotations": anns, "categories": [{"id": 1, "name": "person", "supercategory": "person"}]}
        (root / f"{split}.json").write_text(json.dumps(obj, indent=2), encoding="utf-8")
    return root


def export_cvat_xml(workspace: Path):
    ds = StudioDataset(workspace)
    root = ds.paths.outputs / "cvat_xml"
    _reset_dir(root)
    for split in ("train", "val", "test"):
        annotations = ET.Element("annotations")
        ET.SubElement(annotations, "version").text = "1.1"
        meta = ET.SubElement(annotations, "meta")
        task = ET.SubElement(meta, "task")
        ET.SubElement(task, "name").text = f"AerialPerson-{split}"
        labels = ET.SubElement(task, "labels")
        label = ET.SubElement(labels, "label")
        ET.SubElement(label, "name").text = "person"
        ET.SubElement(label, "color").text = "#2F80ED"
        ET.SubElement(label, "type").text = "any"
        ET.SubElement(label, "attributes")
        for image_id, rec in enumerate(ds.records(split)):
            img = ET.SubElement(annotations, "image", {
                "id": str(image_id), "name": rec["name"], "width": str(rec["width"]), "height": str(rec["height"])
            })
            for b in ds.boxes(split, rec["name"]):
                ET.SubElement(img, "box", {
                    "label": "person", "source": "manual", "occluded": "0", "z_order": "0",
                    "xtl": f"{b['x1']:.3f}", "ytl": f"{b['y1']:.3f}",
                    "xbr": f"{b['x2']:.3f}", "ybr": f"{b['y2']:.3f}",
                })
        ET.ElementTree(annotations).write(root / f"{split}.xml", encoding="utf-8", xml_declaration=True)
    return root


def export_report(workspace: Path):
    ds = StudioDataset(workspace)
    root = ds.paths.reports
    root.mkdir(parents=True, exist_ok=True)
    rows = []
    for split in ("train", "val", "test"):
        for rec in ds.records(split):
            boxes = ds.boxes(split, rec["name"])
            rows.append({
                "split": split, "image": rec["name"], "width": rec["width"], "height": rec["height"],
                "box_count": len(boxes), "is_background": 1 if len(boxes) == 0 else 0,
                "model_boxes": sum(1 for b in boxes if b.get("source") == "model"),
            })
    with (root / "dataset_report.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["split", "image", "width", "height", "box_count", "is_background", "model_boxes"])
        w.writeheader(); w.writerows(rows)
    (root / "dataset_summary.json").write_text(json.dumps(ds.stats(), indent=2), encoding="utf-8")
    return root


def export_all(workspace: Path):
    ds = StudioDataset(workspace)
    result = {
        "yolo": str(export_yolo(workspace)),
        "visdrone": str(export_visdrone(workspace)),
        "coco": str(export_coco(workspace)),
        "cvat_xml": str(export_cvat_xml(workspace)),
        "reports": str(export_report(workspace)),
    }
    package = ds.paths.outputs / "AerialPersonDataset_Final.zip"
    if package.exists():
        package.unlink()
    with zipfile.ZipFile(package, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for folder_name in ("yolo", "visdrone", "coco", "cvat_xml", "reports"):
            folder = ds.paths.outputs / folder_name
            if not folder.exists():
                continue
            for f in folder.rglob("*"):
                if f.is_file():
                    z.write(f, arcname=f.relative_to(ds.paths.outputs).as_posix())
    result["final_zip"] = str(package)
    return result
