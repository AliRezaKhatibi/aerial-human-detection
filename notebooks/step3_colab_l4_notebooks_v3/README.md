# Step 3 - Colab L4 Training Package

This package contains the three final Step-3 training programs selected in Step 1:

1. `train_yolo26s_step3.py`
2. `train_rtdetr_r18_step3.py`
3. `train_bpd_yolon_lfpn_step3.py`

All source code, comments, command-line messages, configuration files, and generated report fields are written in English.

## Project protocol implemented by all three scripts

The controlled baseline is configured for:

- target class: `person` only
- training hardware: Google Colab with NVIDIA L4 GPU
- fixed-budget baseline: 45 epochs
- input size: 1280 x 1280
- seed: 42
- Step-2 Development Pool only for training and internal validation
- private >=1000-image Final Test: **optional at Step 3 and never used for training, tuning, early stopping, or model selection**
- AMP enabled by default on CUDA
- complete experiment provenance and report artifacts
- persistent Google Drive outputs
- checkpoint saved after **every epoch**
- automatic resume from the previous Google Drive `last.pt` checkpoint when available

The private Final Test may not exist yet. That does not stop Step-3 training. If `FREEZE.json` exists, only its metadata is recorded; Final-Test images and annotations are never opened by these scripts.

## Recommended Google Drive project layout

The scripts can auto-discover several layouts, but passing `--project-root` explicitly is the most reliable approach.

Example:

```text
/content/drive/MyDrive/aerial_person_project/
├── workspace/
│   └── aerial-person-data/
│       ├── 03_development/
│       │   ├── data.yaml
│       │   ├── instances_train.json
│       │   └── instances_val.json
│       ├── dataset_manifest.csv
│       └── 90_final_test_v1/          # optional in Step 3
│           └── FREEZE.json            # optional in Step 3
└── runs/
    └── step3/
```

If the Step-2 folder is elsewhere, pass these explicitly:

```text
--project-root
--development-root
--manifest
--data-yaml          # YOLO26s / BPD-YOLOn
--coco-train         # RT-DETR-R18
--coco-val
```

## Colab setup

### 1. Select the L4 GPU

In Colab, select an NVIDIA L4 runtime before final training.

### 2. Mount Google Drive

The scripts try to mount Drive automatically when executed inside Colab. For the most reliable interactive authorization, it is still recommended to mount it once in a notebook cell:

```python
from google.colab import drive
drive.mount('/content/drive')
```

### 3. Put this package in Colab

For example, unzip it to:

```text
/content/step3_colab_l4_v2/
```

The scripts automatically install missing non-PyTorch Python dependencies. Colab's CUDA-enabled PyTorch installation is preserved.

## Preflight before training

Always run `--dry-run` first. The dry run verifies the Development Pool, manifest, class mapping, and train/validation group leakage. The absence of the private Final Test is explicitly allowed.

```bash
python /content/step3_colab_l4_v2/train_yolo26s_step3.py \
  --project-root "/content/drive/MyDrive/aerial_person_project" \
  --dry-run
```

```bash
python /content/step3_colab_l4_v2/train_rtdetr_r18_step3.py \
  --project-root "/content/drive/MyDrive/aerial_person_project" \
  --dry-run
```

```bash
python /content/step3_colab_l4_v2/train_bpd_yolon_lfpn_step3.py \
  --project-root "/content/drive/MyDrive/aerial_person_project" \
  --dry-run
```

## Final baseline training commands

### YOLO26s

```bash
python /content/step3_colab_l4_v2/train_yolo26s_step3.py \
  --project-root "/content/drive/MyDrive/aerial_person_project" \
  --epochs 45 \
  --imgsz 1280 \
  --batch 2 \
  --seed 42 \
  --run-name fixed_budget_baseline
```

### RT-DETR-R18

```bash
python /content/step3_colab_l4_v2/train_rtdetr_r18_step3.py \
  --project-root "/content/drive/MyDrive/aerial_person_project" \
  --epochs 45 \
  --imgsz 1280 \
  --batch 2 \
  --seed 42 \
  --run-name fixed_budget_baseline
```

### BPD-YOLOn/L-FPN

```bash
python /content/step3_colab_l4_v2/train_bpd_yolon_lfpn_step3.py \
  --project-root "/content/drive/MyDrive/aerial_person_project" \
  --epochs 45 \
  --imgsz 1280 \
  --batch 2 \
  --seed 42 \
  --run-name fixed_budget_baseline
```

If a model runs out of L4 memory at batch 2, rerun that model with `--batch 1` and preserve the changed batch size in the Step-3 report. The scripts do not silently change the batch size.

## Google Drive output policy

When `--output-root` is not supplied:

- if `--project-root` is already inside `/content/drive/MyDrive`, outputs are written to `<project-root>/runs/step3/`;
- otherwise outputs are written to `/content/drive/MyDrive/aerial_person_project/step3/runs/`.

Therefore all persistent training artifacts are stored in Google Drive by default.

## Checkpoint policy and resume behavior

### YOLO26s and BPD-YOLOn/L-FPN

`save_period=1` is the default. Ultralytics writes:

```text
<Drive output>/<model>/fixed_budget_baseline/trainer/weights/
├── epoch0.pt
├── epoch1.pt
├── ...
├── best.pt
└── last.pt
```

The exact epoch-file numbering is controlled by the installed Ultralytics version, but a periodic checkpoint is requested for every epoch.

### RT-DETR-R18

A unique checkpoint is written explicitly after every epoch:

```text
<Drive output>/rtdetr_r18/fixed_budget_baseline/02_checkpoints/
├── epochs/
│   ├── epoch_001.pt
│   ├── epoch_002.pt
│   └── ...
├── best.pt
└── last.pt
```

Each RT-DETR checkpoint contains model weights, optimizer state, scheduler state, epoch number, best metric, and CLI configuration.

### Automatic resume

All three scripts use:

```text
--resume auto
```

by default.

If a previous `last.pt` exists for the same model and `--run-name`, training resumes from it. This is designed for Colab disconnects or intentionally interrupted sessions.

To force a fresh run:

```text
--resume none --run-name another_experiment_name
```

To resume an explicit checkpoint:

```text
--resume "/content/drive/MyDrive/.../last.pt"
```

Keep the same target epoch budget when resuming an interrupted Ultralytics run. If a completed experiment must be extended beyond its original budget, create a separately named continuation experiment so that the controlled 45-epoch baseline remains auditable.

## Private Final Test behavior

The private >=1000-image dataset is reserved for final model testing. It is not required to exist during Step 3.

The Step-3 scripts:

- do not load its images;
- do not load its annotations;
- do not use it for validation;
- do not use it for threshold selection;
- do not use it for early stopping;
- do not use it for augmentation decisions;
- continue normally when the Final Test has not been collected or frozen yet.

## Step-3 artifacts saved for the final report

Each model run creates a structured Drive directory similar to:

```text
runs/step3/<model>/fixed_budget_baseline/
├── 00_audit/
│   ├── environment.json
│   ├── dataset_snapshot.json
│   └── resume_history.jsonl
├── 01_config/
│   ├── cli_args.json
│   ├── resolved_protocol.json
│   ├── model_metadata.json
│   └── train_kwargs.json              # YOLO-family scripts
├── 02_checkpoints/
│   ├── epochs/                        # explicit RT-DETR epoch checkpoints
│   ├── best.pt
│   └── last.pt
├── 03_metrics/
│   ├── standardized_coco_metrics.json
│   ├── operating_point_metrics.json
│   ├── failure_ranking.csv
│   └── training history/results
├── 04_curves/
├── 05_predictions/
│   └── internal_val_predictions.coco.json
├── 06_failure_samples/
├── 07_logs/
├── STEP3_RUN_REPORT.json
└── STEP3_RUN_REPORT.md
```

YOLO-family epoch checkpoints are additionally retained by the Ultralytics trainer under `trainer/weights/`.

The generated report artifacts contain the information required to write Step 3, including:

- model identity and implementation provenance;
- pretrained checkpoint information;
- Step-2 dataset and manifest fingerprints;
- split and leakage audit;
- class mapping;
- seed, epoch budget, batch, image size, workers;
- optimizer and learning-rate settings;
- augmentation settings;
- installed Python/package versions;
- detected GPU, CUDA and PyTorch environment;
- explicit NVIDIA L4 environment audit;
- best epoch and selection metric;
- Precision, Recall, F1, AP50 and mAP50-95;
- tiny/small/medium/large size-aware metrics;
- training duration;
- peak VRAM;
- internal-validation latency;
- best/last checkpoint hashes;
- predictions used for standardized evaluation;
- failure ranking and visual failure samples;
- resume history;
- confirmation that private Final-Test content was not used.

## Model-specific notes

### YOLO26s

The primary baseline remains the unmodified YOLO26s selected in Step 1. P2, tiling, and SAHI are not mixed into this baseline; those must be separately named ablations.

### RT-DETR-R18

The script uses the RT-DETR-R18 checkpoint through Hugging Face Transformers, changes the detection label space to one class (`person`), trains from the Step-2 COCO files, and evaluates against the same internal validation split.

Large per-epoch prediction JSON files are not kept by default. Per-epoch metrics and model checkpoints are retained. The final internal-validation prediction file is always stored in Drive. Use `--save-epoch-predictions` only when those intermediate JSON files are specifically required.

### BPD-YOLOn/L-FPN

The included implementation remains the project reimplementation described in the Step-1 package, rather than being presented as official author code. The controlled baseline uses the same 45-epoch project budget. The separate paper-budget experiment can still be started with:

```bash
python /content/step3_colab_l4_v2/train_bpd_yolon_lfpn_step3.py \
  --project-root "/content/drive/MyDrive/aerial_person_project" \
  --native-paper-budget \
  --run-name paper_native_300e \
  --resume auto
```

Do not merge that 300-epoch result into the fixed-budget table as if the compute budgets were equal.

## What to send back after training

For the final Step-3 report, preserve the entire three Drive run folders. At minimum, provide the three `STEP3_RUN_REPORT.json` files plus the corresponding `03_metrics`, `04_curves`, and `06_failure_samples` folders.
