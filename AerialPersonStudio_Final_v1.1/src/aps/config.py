from __future__ import annotations
from dataclasses import asdict, dataclass, field
import json
from pathlib import Path


@dataclass
class PrepareConfig:
    video_frame_interval_seconds: float = 1.0
    min_width: int = 320
    min_height: int = 240
    blur_filter_enabled: bool = True
    blur_threshold: float = 35.0
    black_filter_enabled: bool = True
    black_mean_threshold: float = 8.0
    black_std_threshold: float = 4.0
    duplicate_filter_enabled: bool = True
    phash_hamming_threshold: int = 4
    train_ratio: float = 0.80
    val_ratio: float = 0.10
    test_ratio: float = 0.10
    jpeg_quality: int = 95


@dataclass
class AutoLabelConfig:
    model_path: str = "models/prelabel/yolo26s_visdrone_best.pt"
    confidence: float = 0.10
    iou: float = 0.70
    imgsz: int = 1280
    max_det: int = 3000
    device: str = "auto"
    tiled_inference: bool = False
    tile_size: int = 960
    tile_overlap: float = 0.20


@dataclass
class AppConfig:
    prepare: PrepareConfig = field(default_factory=PrepareConfig)
    autolabel: AutoLabelConfig = field(default_factory=AutoLabelConfig)

    @classmethod
    def load(cls, path: Path) -> "AppConfig":
        if not path.exists():
            return cls()
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            prepare=PrepareConfig(**data.get("prepare", {})),
            autolabel=AutoLabelConfig(**data.get("autolabel", {})),
        )

    def save(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
