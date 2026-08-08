from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class WorkspacePaths:
    root: Path

    @property
    def raw(self): return self.root / "raw"
    @property
    def raw_images(self): return self.raw / "images"
    @property
    def raw_videos(self): return self.raw / "videos"
    @property
    def work(self): return self.root / "work"
    @property
    def candidates(self): return self.work / "candidates"
    @property
    def standardized(self): return self.work / "standardized"
    @property
    def cvat_upload(self): return self.work / "cvat_upload"
    @property
    def studio(self): return self.work / "studio"
    @property
    def studio_images(self): return self.studio / "images"
    @property
    def studio_trash(self): return self.studio / "trash"
    @property
    def manifest(self): return self.work / "manifest.csv"
    @property
    def dataset_json(self): return self.studio / "dataset.json"
    @property
    def annotations_json(self): return self.studio / "annotations.json"
    @property
    def reports(self): return self.root / "outputs" / "reports"
    @property
    def outputs(self): return self.root / "outputs"
    @property
    def imports(self): return self.root / "imports"

    def ensure(self):
        for p in [
            self.raw_images, self.raw_videos, self.work, self.candidates,
            self.standardized, self.cvat_upload, self.studio,
            self.studio_images, self.studio_trash, self.outputs,
            self.reports, self.imports / "cvat",
        ]:
            p.mkdir(parents=True, exist_ok=True)
        for split in ("train", "val", "test"):
            (self.studio_images / split).mkdir(parents=True, exist_ok=True)
            (self.studio_trash / split).mkdir(parents=True, exist_ok=True)
