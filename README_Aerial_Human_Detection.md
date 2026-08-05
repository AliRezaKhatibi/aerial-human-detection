<div align="center">

# 🚁 Aerial Human Detection

### Real-time human detection, tracking, and analysis in drone and UAV imagery

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/downloads/)
[![PyTorch 2.0+](https://img.shields.io/badge/PyTorch-2.0%2B-EE4C2C?logo=pytorch&logoColor=white)](https://pytorch.org/)
[![Ultralytics](https://img.shields.io/badge/Ultralytics-YOLO-111F68?logo=ultralytics&logoColor=white)](https://www.ultralytics.com/)
[![CUDA](https://img.shields.io/badge/CUDA-Enabled-76B900?logo=nvidia&logoColor=white)](https://developer.nvidia.com/cuda-zone)
[![License: MIT](https://img.shields.io/badge/License-MIT-2EA44F.svg)](LICENSE)
[![Status](https://img.shields.io/badge/Status-Active%20Development-F59E0B.svg)](#project-status)

**A research-driven computer vision system for detecting and tracking people in aerial videos captured by drones, UAVs, and elevated cameras.**

The project is designed around difficult real-world conditions such as **tiny targets, high-altitude imagery, dense crowds, camera motion, occlusion, motion blur, and 4K video streams**.

[Overview](#-overview) ·
[Features](#-key-features) ·
[Architecture](#-system-architecture) ·
[Installation](#-installation) ·
[Usage](#-usage) ·
[Roadmap](#-roadmap)

</div>

---

## 📌 Table of Contents

- [Overview](#-overview)
- [Project Goals](#-project-goals)
- [Key Features](#-key-features)
- [System Architecture](#-system-architecture)
- [Model Strategy](#-model-strategy)
- [Datasets](#-datasets)
- [Repository Structure](#-repository-structure)
- [Installation](#-installation)
- [Quick Start](#-quick-start)
- [Training](#-training)
- [Evaluation](#-evaluation)
- [Tracking](#-tracking)
- [Graphical User Interface](#-graphical-user-interface)
- [Deployment and Optimization](#-deployment-and-optimization)
- [Output Files](#-output-files)
- [Project Status](#-project-status)
- [Roadmap](#-roadmap)
- [Contributing](#-contributing)
- [Citation](#-citation)
- [License](#-license)

---

# 🔭 Overview

Detecting people from aerial imagery is significantly more difficult than standard pedestrian detection from ground-level cameras.

In drone and UAV footage, a person may occupy only a few pixels and can easily be confused with background objects, shadows, road markings, vegetation, or visual noise. The problem becomes harder when the camera is moving, people are close to one another, or the video is recorded from high altitude.

This project develops an end-to-end pipeline for:

- detecting people in aerial images and videos;
- tracking each detected person across frames;
- assigning stable track identities;
- selecting and following one or more specific subjects;
- analyzing performance and exporting structured results;
- running the complete system through a modern graphical interface;
- deploying optimized inference on NVIDIA hardware.

The current development direction focuses on a **single-class person detector** trained on aerial data and optimized for real-time or near-real-time inference.

---

# 🎯 Project Goals

The main goals of the project are:

1. **High recall for very small people**  
   Detect people that occupy only a small region of high-resolution aerial frames.

2. **Stable multi-object tracking**  
   Maintain consistent track IDs despite occlusion, missed detections, camera motion, and crowd interactions.

3. **Real-time inference**  
   Target practical performance on GPUs such as the NVIDIA RTX 3070.

4. **Single-model deployment**  
   Avoid unnecessary model ensembles in production and keep the inference pipeline maintainable.

5. **Production-oriented optimization**  
   Support PyTorch, ONNX, TensorRT, FP16 inference, hardware video decoding, and hardware encoding.

6. **User-friendly operation**  
   Provide a graphical interface for video upload, live processing, target selection, output management, and model monitoring.

7. **Reproducible research**  
   Store training settings, test results, model hashes, experiment summaries, and deployment metadata.

---

# ✨ Key Features

## Detection

- Person-only aerial object detection
- Support for high-resolution images and 4K videos
- Small-object-aware training pipeline
- Full-frame inference
- Adaptive tiling for difficult scenes
- Configurable confidence and IoU thresholds
- PyTorch, ONNX, and TensorRT deployment paths

## Tracking

- ByteTrack integration
- Planned BoT-SORT support
- Stable track identity recovery
- Lost-track retention
- Trajectory history
- Multi-subject selection
- Click-to-focus tracking
- Highlight selected subjects with red bounding boxes
- Dim or blur non-selected detections

## User Interface

- Persian and English language support
- RTL and LTR layout
- Live processing preview
- GPU, CUDA, WebSocket, and model status
- Real-time FPS and inference latency
- Active-person and unique-person counters
- Subject selection during live processing
- Settings persistence
- Fullscreen preview
- Searchable navigation
- Export and result management

## Reporting

- Annotated output video
- CSV tracking log
- JSON detection report
- Model metadata
- SHA256 model fingerprint
- Training summary
- Test metrics
- Deployment benchmark
- Runtime logs

## Deployment

- NVIDIA CUDA inference
- FP16 inference
- ONNX Runtime
- TensorRT export
- Docker-ready structure
- Windows desktop packaging roadmap
- RTX 3070 optimization target

---

# 🧩 System Architecture

```mermaid
flowchart LR
    A[Input Image / Video / Stream]
    B[Video Decode]
    C[Frame Preprocessing]
    D[Person Detector]
    E[Adaptive Tiling]
    F[Detection Fusion]
    G[Multi-Object Tracker]
    H[Stable ID Layer]
    I[Subject Focus Manager]
    J[Visualization]
    K[Video Encoder]
    L[CSV / JSON / Reports]
    M[Live WebSocket Preview]
    N[GUI]

    A --> B
    B --> C
    C --> D
    C --> E
    E --> D
    D --> F
    F --> G
    G --> H
    H --> I
    I --> J
    J --> K
    H --> L
    J --> M
    M --> N
```

## Processing Pipeline

```text
Input video
   ↓
Decode frame
   ↓
Resize and normalize
   ↓
Full-frame person detection
   ↓
Optional adaptive tiles
   ↓
Merge detections
   ↓
Multi-object tracking
   ↓
Stable ID reconciliation
   ↓
Selected-subject highlighting
   ↓
Live preview and output encoding
   ↓
CSV, JSON, video, logs, and summary
```

---

# 🧠 Model Strategy

## Primary Model Direction

The primary research direction is:

```text
YOLO26s-P2
+ Person-only training
+ P2 / P3 / P4 / P5 detection scales
+ Context tiles
+ Controlled Mosaic augmentation
+ Final natural-image fine-tuning
+ TensorRT FP16 deployment
```

The P2 detection branch is intended to preserve higher-resolution spatial features for very small people.

## Detection Scales

| Feature Level | Stride | Primary Use |
|---|---:|---|
| P2 | 4 | Very small people |
| P3 | 8 | Small people |
| P4 | 16 | Medium targets |
| P5 | 32 | Large or close targets |

## Why a Small Model?

Aerial video analytics is not limited to the detector. The complete pipeline also includes:

- video decoding;
- image resizing;
- data transfer between CPU and GPU;
- non-maximum suppression or end-to-end decoding;
- tracking;
- stable-ID recovery;
- drawing;
- preview generation;
- WebSocket transfer;
- output video encoding.

A smaller detector leaves more compute budget for these operations and is better suited to real-time deployment.

## Supported and Planned Model Families

| Model Family | Role |
|---|---|
| YOLO26s-P2 | Primary final model |
| YOLO26s | Fast baseline |
| YOLO26m-P2 | Accuracy-oriented research model |
| YOLO11 | Stable external baseline |
| YOLOv9-P2 | Small-object comparison |
| RT-DETR | Transformer-based baseline |
| Faster R-CNN | Two-stage baseline |
| SSD | Lightweight historical baseline |

> The production system is intended to use one optimized detector at a time.

---

# 🗃 Datasets

The project is designed around aerial datasets with people visible from elevated viewpoints.

## Primary Dataset

### VisDrone

VisDrone contains aerial imagery collected under diverse conditions, including:

- different cities;
- variable altitude;
- different camera angles;
- dense scenes;
- occlusion;
- motion blur;
- illumination changes;
- small and very small objects.

For the person-only pipeline, the human-related labels are converted into a unified class:

```text
pedestrian + people → person
```

## Additional Datasets

| Dataset | Intended Use |
|---|---|
| VisDrone | Primary training and evaluation |
| UAVDT | Domain-shift and aerial traffic scenes |
| Okutama-Action | High-altitude human detection and activity scenes |
| Custom aerial samples | Real-world qualitative testing |

## Dataset Policy

- Train, validation, and test splits must remain separate.
- Test images must not be used during training.
- Context tiles are generated only from the training split.
- Validation is used for model selection.
- Test is used only for final evaluation.
- All dataset licenses must be respected.

---

# 🗂 Repository Structure

```text
aerial-human-detection/
├── assets/
│   ├── screenshots/
│   ├── demos/
│   └── diagrams/
│
├── data/
│   ├── raw/
│   ├── processed/
│   ├── annotations/
│   ├── splits/
│   └── aerial-samples/
│
├── notebooks/
│   ├── dataset_analysis/
│   ├── model_training/
│   ├── benchmarking/
│   └── deployment/
│
├── src/
│   ├── data/
│   │   ├── converters/
│   │   ├── loaders/
│   │   ├── tiling/
│   │   └── validation/
│   │
│   ├── models/
│   │   ├── detection/
│   │   ├── tracking/
│   │   └── configs/
│   │
│   ├── training/
│   │   ├── train.py
│   │   ├── resume.py
│   │   └── callbacks.py
│   │
│   ├── evaluation/
│   │   ├── metrics.py
│   │   ├── benchmark.py
│   │   └── reports.py
│   │
│   ├── inference/
│   │   ├── image.py
│   │   ├── video.py
│   │   ├── stream.py
│   │   └── pipeline.py
│   │
│   ├── tracking/
│   │   ├── bytetrack.py
│   │   ├── botsort.py
│   │   ├── stable_id.py
│   │   └── subject_focus.py
│   │
│   ├── backend/
│   │   ├── api/
│   │   ├── websocket/
│   │   ├── jobs/
│   │   └── storage/
│   │
│   └── gui/
│       ├── frontend/
│       └── desktop/
│
├── configs/
│   ├── models/
│   ├── trackers/
│   ├── training/
│   └── deployment/
│
├── models/
│   ├── pytorch/
│   ├── onnx/
│   └── tensorrt/
│
├── runtime/
│   ├── uploads/
│   ├── outputs/
│   ├── previews/
│   ├── logs/
│   └── database/
│
├── scripts/
│   ├── setup/
│   ├── training/
│   ├── export/
│   ├── benchmark/
│   └── deployment/
│
├── tests/
│   ├── unit/
│   ├── integration/
│   └── performance/
│
├── docs/
│   ├── architecture/
│   ├── dataset/
│   ├── training/
│   ├── deployment/
│   └── user-guide/
│
├── docker/
├── results/
├── .github/
├── README.md
├── LICENSE
├── pyproject.toml
└── requirements.txt
```

---

# ⚙️ Installation

## Requirements

- Python 3.10 or newer
- NVIDIA GPU recommended
- CUDA-compatible PyTorch
- FFmpeg
- Git
- Node.js for the graphical interface
- Rust only for the future Tauri desktop package

## Clone the Repository

```bash
git clone https://github.com/your-username/aerial-human-detection.git
cd aerial-human-detection
```

## Create a Python Environment

### Linux / macOS

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Verify CUDA

```bash
python -c "import torch; print('Torch:', torch.__version__); print('CUDA:', torch.cuda.is_available()); print('GPU:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU')"
```

Expected output:

```text
CUDA: True
GPU: NVIDIA ...
```

## Install FFmpeg

### Ubuntu

```bash
sudo apt update
sudo apt install ffmpeg
```

### Windows

Install FFmpeg and add it to the system `PATH`.

Verification:

```bash
ffmpeg -version
```

---

# 🚀 Quick Start

## Image Inference

```bash
python -m src.inference.image \
  --model models/pytorch/best.pt \
  --source data/aerial-samples/sample.jpg \
  --imgsz 1280 \
  --conf 0.25 \
  --device 0
```

## Video Inference

```bash
python -m src.inference.video \
  --model models/pytorch/best.pt \
  --source data/aerial-samples/sample.mp4 \
  --tracker configs/trackers/bytetrack.yaml \
  --imgsz 1280 \
  --conf 0.25 \
  --save-video \
  --save-csv \
  --save-json
```

## Stream Inference

```bash
python -m src.inference.stream \
  --model models/pytorch/best.pt \
  --source "rtsp://username:password@camera-address/stream" \
  --device 0
```

> RTSP support is planned for a later release and may not be enabled in the current development branch.

---

# 🏋️ Training

## Training Philosophy

The training pipeline is designed around:

- transfer learning;
- high-resolution training;
- person-only labels;
- P2 small-object detection;
- context-aware tiles;
- controlled Mosaic augmentation;
- natural-image fine-tuning;
- reproducible seeds;
- fixed train/validation/test splits;
- final test-only evaluation.

## Recommended Three-Stage Training

| Stage | Resolution | Epochs | Dataset | Mosaic | Purpose |
|---|---:|---:|---|---|---|
| P2 warm-up | 960 | 8 | Full scenes | Enabled | Initialize the P2 branch |
| Main training | 1280 | 32 | Full + context tiles | Enabled | Learn very small people |
| Final fine-tuning | 1280 | 10 | Full scenes | Disabled | Improve localization |

## Example Training Command

```bash
python -m src.training.train \
  --model configs/models/yolo26s-p2-person.yaml \
  --data configs/datasets/visdrone-person.yaml \
  --epochs 50 \
  --imgsz 1280 \
  --device 0 \
  --single-cls
```

## Reproducibility

Every training run should store:

```text
best.pt
last.pt
args.yaml
results.csv
results.png
PR_curve.png
F1_curve.png
confusion_matrix.png
environment.json
model_metadata.json
SHA256.txt
```

---

# 📏 Evaluation

The project reports the following metrics:

| Metric | Description |
|---|---|
| Precision | Fraction of predicted detections that are correct |
| Recall | Fraction of ground-truth people that are detected |
| mAP50 | Mean average precision at IoU 0.50 |
| mAP50-95 | Mean average precision across IoU 0.50–0.95 |
| Inference time | Detector runtime per frame |
| End-to-end FPS | Full pipeline throughput |
| ID switches | Track identity changes |
| IDF1 | Identity consistency |
| MOTA | Multi-object tracking accuracy |
| HOTA | Detection and association quality |
| Fragmentation | Number of broken trajectories |

## Important Evaluation Rule

The value shown as confidence in the interface is not the model's true accuracy. Proper accuracy requires annotated ground truth.

## Run Detection Evaluation

```bash
python -m src.evaluation.benchmark \
  --model models/pytorch/best.pt \
  --data configs/datasets/visdrone-person.yaml \
  --split test \
  --imgsz 1280 \
  --device 0
```

## Run Tracking Evaluation

```bash
python -m src.evaluation.tracking \
  --detections results/detections \
  --ground-truth data/annotations/test \
  --metrics idf1 mota hota ids fragmentation
```

---

# 🧭 Tracking

The tracking subsystem is designed to operate after person detection.

## Current Tracker

- ByteTrack

## Planned Tracker

- BoT-SORT
- Global motion compensation
- Optional appearance-based ReID

## Stable ID Layer

The stable-ID layer aims to reduce identity changes caused by:

- short missed detections;
- partial occlusion;
- camera motion;
- scale changes;
- people crossing each other;
- temporary tracker loss.

It may use:

- recent trajectory;
- center distance;
- IoU;
- bounding-box dimensions;
- motion prediction;
- lost-track age;
- optional appearance embedding.

## Subject Focus Mode

During live processing, the user can select one or more track IDs.

Selected subjects can be displayed with:

- red bounding boxes;
- emphasized labels;
- trajectory trails;
- focused status panels.

Other detections can be:

- dimmed;
- faded;
- blurred;
- hidden from labels;
- shown with reduced opacity.

---

# 🖥️ Graphical User Interface

The interface is designed as a professional desktop-oriented dashboard.

## Main Screens

- Dashboard
- New analysis
- Live processing
- Results
- Model management
- Settings
- System status

## Live Processing Information

- Actual inference device
- CUDA availability
- GPU model
- WebSocket connection
- Processing profile
- Active persons
- Unique persons
- Average confidence
- Tile count
- Model inference time
- End-to-end FPS
- Frame progress
- Processing state

## Processing Profiles

### Fast

```text
Full-frame inference
Reduced input size
No tiling
Low-latency preview
```

### Balanced

```text
Full-frame inference
Limited adaptive tiling
Tracking and stable IDs
Moderate preview rate
```

### Accuracy

```text
High-resolution inference
More adaptive tiles
Stricter analysis
Higher computation cost
```

---

# ⚡ Deployment and Optimization

## Supported Model Formats

| Format | Use |
|---|---|
| `.pt` | Training and reference inference |
| `.onnx` FP32 | Portable deployment |
| `.onnx` FP16 | Reduced memory and faster GPU inference |
| `.engine` FP16 | Maximum NVIDIA TensorRT performance |

## Recommended Deployment Path

```text
best.pt
   ↓
ONNX FP32
   ↓
ONNX FP16
   ↓
TensorRT FP16
```

## TensorRT Recommendation

TensorRT engines should be built on the target deployment GPU.

For example, an engine intended for an RTX 3070 should be generated on the RTX 3070 deployment system.

## Video Pipeline Optimization

Recommended optimized pipeline:

```text
NVDEC hardware decode
   ↓
GPU preprocessing
   ↓
TensorRT FP16 inference
   ↓
Tracking
   ↓
GPU or lightweight drawing
   ↓
NVENC hardware encode
```

## Performance Target

The project targets:

```text
10+ FPS end-to-end on NVIDIA RTX 3070
```

This target includes detection, tracking, visualization, and output handling. Actual performance depends on:

- input resolution;
- video codec;
- model size;
- tiling mode;
- preview frequency;
- output encoding;
- CPU;
- storage;
- TensorRT availability.

No benchmark should be considered final until it is measured on the target system under the full production pipeline.

---

# 📦 Output Files

Each processing job should generate an isolated output directory:

```text
runtime/outputs/<job-id>/
├── annotated_video.mp4
├── detections.csv
├── detections.json
├── tracks.csv
├── summary.json
├── settings.json
├── model_metadata.json
├── thumbnail.jpg
└── processing.log
```

## CSV Example

```csv
frame,time_s,track_id,x1,y1,x2,y2,confidence,selected
1,0.033,12,412,188,438,244,0.87,false
1,0.033,18,801,320,826,375,0.81,true
```

## JSON Example

```json
{
  "job_id": "example-job-id",
  "model": "YOLO26s-P2",
  "device": "cuda:0",
  "input_resolution": [3840, 2160],
  "inference_size": 1280,
  "frames_processed": 2400,
  "unique_tracks": 38,
  "selected_tracks": [18],
  "outputs": {
    "video": "annotated_video.mp4",
    "csv": "tracks.csv",
    "json": "detections.json"
  }
}
```

---

# 🚧 Project Status

**Current status: Active development**

| Component | Status |
|---|---|
| Dataset preparation | In progress |
| Person-only VisDrone conversion | Implemented |
| YOLO baseline training | Implemented |
| YOLO26s-P2 training pipeline | In progress |
| ByteTrack integration | Implemented |
| Stable ID recovery | In progress |
| Subject focus selection | Implemented / improving |
| WebSocket live preview | Implemented |
| Persian and English interface | Implemented / improving |
| ONNX export | Implemented |
| TensorRT deployment | Planned |
| BoT-SORT integration | Planned |
| SQLite job history | Planned |
| Tauri desktop package | Planned |
| Windows installer | Planned |

---

# 🗺 Roadmap

## Phase 1 — Data and Baselines

- [x] Collect aerial datasets
- [x] Convert VisDrone labels
- [x] Merge human-related classes
- [x] Create person-only split
- [x] Train initial YOLO baseline
- [ ] Complete external baseline comparison
- [ ] Publish reproducible benchmark table

## Phase 2 — Small-Object Detection

- [x] High-resolution training
- [x] Context tile generation
- [x] Adaptive tiling prototype
- [ ] Train YOLO26s-P2
- [ ] Evaluate very-small-object recall
- [ ] Compare YOLO26s vs YOLO26s-P2
- [ ] Compare YOLO26s-P2 vs YOLO26m-P2

## Phase 3 — Tracking

- [x] ByteTrack integration
- [x] Track ID visualization
- [x] Multi-subject selection
- [x] Stable-ID prototype
- [ ] Global motion compensation
- [ ] BoT-SORT integration
- [ ] Optional ReID
- [ ] Ground-truth tracking benchmark

## Phase 4 — Interface

- [x] React frontend
- [x] FastAPI backend
- [x] WebSocket live preview
- [x] Video upload
- [x] Live processing dashboard
- [x] Persian and English support
- [x] Settings persistence
- [ ] Complete results page
- [ ] Model inspector
- [ ] Performance profiler
- [ ] Job history database

## Phase 5 — Optimization

- [x] CUDA inference
- [x] ONNX export
- [ ] TensorRT FP16
- [ ] NVDEC decode
- [ ] NVENC encode
- [ ] Asynchronous pipeline
- [ ] Batched tile inference
- [ ] RTX 3070 benchmark

## Phase 6 — Desktop Release

- [ ] Tauri integration
- [ ] Python sidecar
- [ ] Windows packaging
- [ ] Installer
- [ ] Automatic environment validation
- [ ] Release documentation

---

# 🧪 Testing

Run unit tests:

```bash
pytest tests/unit -v
```

Run integration tests:

```bash
pytest tests/integration -v
```

Run the full test suite:

```bash
pytest -v
```

Run frontend tests:

```bash
npm --prefix frontend test
```

Build the frontend:

```bash
npm --prefix frontend run build
```

---

# 🐳 Docker

A future production container may include:

- CUDA runtime;
- PyTorch or TensorRT;
- FastAPI backend;
- FFmpeg;
- model files;
- runtime directories;
- health checks.

Example:

```bash
docker build -t aerial-human-detection .
docker run --gpus all -p 8000:8000 aerial-human-detection
```

> Docker support is part of the project roadmap and may not be production-ready in the current branch.

---

# 🔒 Privacy and Responsible Use

This project processes imagery that may contain people. Users are responsible for:

- complying with local privacy laws;
- obtaining required permissions;
- avoiding unlawful surveillance;
- securing uploaded videos and outputs;
- applying retention and deletion policies;
- preventing misuse of tracking data.

The system is intended for research, safety, monitoring, search-and-rescue, analytics, and other lawful applications.

---

# 🤝 Contributing

Contributions are welcome.

Recommended workflow:

```bash
git checkout -b feature/your-feature
git add .
git commit -m "Add your feature"
git push origin feature/your-feature
```

Then open a pull request.

Please include:

- a clear explanation;
- affected files;
- test results;
- screenshots for UI changes;
- benchmark results for performance changes;
- documentation updates.

## Contribution Areas

- small-object detection;
- aerial dataset preparation;
- tracking;
- ReID;
- global motion compensation;
- ONNX and TensorRT;
- video decoding and encoding;
- user interface;
- testing;
- documentation.

---

# 🐞 Bug Reports

When reporting a bug, include:

```text
Operating system
Python version
PyTorch version
Ultralytics version
CUDA version
GPU model
Driver version
Input video information
Selected profile
Error log
Steps to reproduce
```

For GPU issues, include:

```bash
nvidia-smi
```

and:

```bash
python -c "import torch; print(torch.__version__); print(torch.version.cuda); print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU')"
```

---

# 📚 Documentation

Planned documentation sections:

- Dataset preparation guide
- VisDrone person-only conversion
- YOLO26s-P2 training guide
- Tracking configuration
- GUI user guide
- ONNX export
- TensorRT deployment
- RTX 3070 optimization
- Troubleshooting
- Benchmark methodology

---

# 📝 Citation

When using this project in academic work, cite the repository:

```bibtex
@software{aerial_human_detection,
  title        = {Aerial Human Detection},
  author       = {Project Contributors},
  year         = {2026},
  url          = {https://github.com/your-username/aerial-human-detection},
  note         = {Real-time human detection and tracking in aerial imagery}
}
```

Replace the author and repository URL with the final project information.

---

# 📄 License

This repository is released under the [MIT License](LICENSE), unless a subdirectory, model, dataset, or third-party component specifies a different license.

Important:

- VisDrone and other datasets may have their own usage restrictions.
- Pretrained weights may inherit restrictions from their source dataset.
- Third-party libraries retain their original licenses.
- Commercial users must verify dataset and model licensing separately.

---

# 🙏 Acknowledgements

This project builds on research and open-source work from:

- Ultralytics
- PyTorch
- VisDrone
- ByteTrack
- BoT-SORT
- OpenCV
- ONNX Runtime
- NVIDIA TensorRT
- FastAPI
- React
- FFmpeg
- the aerial computer vision research community

---

<div align="center">

### 🚁 Built for small targets, moving cameras, and real-world aerial video

**Detection · Tracking · Subject Focus · GPU Acceleration · Deployment**

</div>