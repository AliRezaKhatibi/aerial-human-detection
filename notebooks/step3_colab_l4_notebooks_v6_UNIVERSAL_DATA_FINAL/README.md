# Step 3 — Colab L4 V6 UNIVERSAL DATA FINAL

V6 removes the hard dependency on the directory name `03_development`.

Accepted labeled Train/Val inputs:

- Canonical Step-2 `03_development`
- YOLO: `train/images`, `train/labels`, `val/images`, `val/labels`
- YOLO: `images/train`, `labels/train`, `images/val`, `labels/val`
- Valid `data.yaml` / `dataset.yaml`
- COCO train/val JSON pair

For RT-DETR-R18, if only a person-only YOLO Train/Val export exists, the notebook automatically
creates runtime COCO JSON files.

The private >=1000-image Final Test is never required during Step 3 and is not used for training.

If the Data Locator cell reports no valid Train/Val signature, the issue is not the model code:
Step 2 has not yet produced/uploaded a labeled development dataset, and training cannot start.
