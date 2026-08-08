from __future__ import annotations
import json
import shutil
import zipfile
from pathlib import Path
from typing import Any
from PIL import Image

from .paths import WorkspacePaths

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}


class StudioDataset:
    def __init__(self, workspace: Path):
        self.paths = WorkspacePaths(Path(workspace).resolve())
        self.paths.ensure()
        self.dataset: dict[str, Any] = {
            "version": 1,
            "classes": ["person"],
            "splits": {"train": [], "val": [], "test": []},
        }
        self.annotations: dict[str, list[dict[str, Any]]] = {}
        self.load()

    def load(self):
        if self.paths.dataset_json.exists():
            self.dataset = json.loads(self.paths.dataset_json.read_text(encoding="utf-8"))
        if self.paths.annotations_json.exists():
            self.annotations = json.loads(self.paths.annotations_json.read_text(encoding="utf-8"))
        self.dataset.setdefault("classes", ["person"])
        self.dataset.setdefault("splits", {})
        for split in ("train", "val", "test"):
            self.dataset["splits"].setdefault(split, [])

    def save(self):
        self.paths.studio.mkdir(parents=True, exist_ok=True)
        self.paths.dataset_json.write_text(json.dumps(self.dataset, indent=2), encoding="utf-8")
        self.paths.annotations_json.write_text(json.dumps(self.annotations, indent=2), encoding="utf-8")

    @staticmethod
    def key(split: str, name: str) -> str:
        return f"{split}/{name}"

    def records(self, split: str):
        return self.dataset["splits"].get(split, [])

    def record(self, split: str, name: str):
        for r in self.records(split):
            if r["name"] == name:
                return r
        return None

    def image_path(self, record: dict[str, Any]) -> Path:
        p = Path(record["path"])
        return p if p.is_absolute() else self.paths.root / p

    def boxes(self, split: str, name: str):
        return self.annotations.get(self.key(split, name), [])

    def set_boxes(self, split: str, name: str, boxes: list[dict[str, Any]]):
        self.annotations[self.key(split, name)] = boxes
        self.save()

    def delete_image(self, split: str, name: str):
        record = self.record(split, name)
        if not record:
            return False
        src = self.image_path(record)
        trash = self.paths.studio_trash / split / name
        trash.parent.mkdir(parents=True, exist_ok=True)
        if src.exists():
            if trash.exists():
                trash.unlink()
            shutil.move(str(src), str(trash))
        self.dataset["splits"][split] = [r for r in self.records(split) if r["name"] != name]
        self.annotations.pop(self.key(split, name), None)
        self.save()
        return True

    def clear_annotations(self, split: str | None = None):
        if split is None:
            self.annotations.clear()
        else:
            prefix = f"{split}/"
            self.annotations = {k: v for k, v in self.annotations.items() if not k.startswith(prefix)}
        self.save()

    def import_existing_cvat_zips(self, replace_studio: bool = True, progress=None):
        """Load the project's current train/val/test ZIPs into the editable Studio dataset."""
        if replace_studio:
            for split in ("train", "val", "test"):
                dst = self.paths.studio_images / split
                if dst.exists():
                    shutil.rmtree(dst)
                dst.mkdir(parents=True, exist_ok=True)
            self.dataset = {"version": 1, "classes": ["person"], "splits": {"train": [], "val": [], "test": []}}
            self.annotations = {}

        total = 0
        for split in ("train", "val", "test"):
            zp = self.paths.cvat_upload / f"{split}_images.zip"
            if not zp.exists():
                continue
            with zipfile.ZipFile(zp, "r") as z:
                members = [m for m in z.infolist() if not m.is_dir() and Path(m.filename).suffix.lower() in IMAGE_EXTS]
                for idx, m in enumerate(members, start=1):
                    name = Path(m.filename).name
                    dst = self.paths.studio_images / split / name
                    with z.open(m) as src, open(dst, "wb") as out:
                        shutil.copyfileobj(src, out)
                    with Image.open(dst) as im:
                        w, h = im.size
                    rel = dst.relative_to(self.paths.root).as_posix()
                    self.dataset["splits"][split].append({
                        "name": name, "path": rel, "width": w, "height": h,
                        "source_id": "imported_cvat_zip", "source_type": "prepared",
                    })
                    total += 1
                    if progress:
                        progress(split, idx, len(members), name)
        self.save()
        return total

    def stats(self):
        result = {}
        for split in ("train", "val", "test"):
            recs = self.records(split)
            boxes = sum(len(self.boxes(split, r["name"])) for r in recs)
            positive = sum(bool(self.boxes(split, r["name"])) for r in recs)
            result[split] = {"images": len(recs), "boxes": boxes, "positive_images": positive}
        result["total_images"] = sum(result[s]["images"] for s in ("train", "val", "test"))
        result["total_boxes"] = sum(result[s]["boxes"] for s in ("train", "val", "test"))
        return result
