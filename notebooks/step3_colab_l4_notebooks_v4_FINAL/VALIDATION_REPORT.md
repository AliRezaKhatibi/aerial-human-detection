# Step 3 Colab L4 — Validation Report

Package: v4 FINAL

## Corrections applied

1. Placeholder or stale development paths such as `/path/to/your/03_development_directory` are no longer treated as mandatory real paths. The scripts fall back to deterministic Step-2 auto-discovery.
2. Step-2 `03_development` discovery works from the project tree and, in Colab, from Google Drive.
3. The private >=1000-image Final Test is optional in Step 3. Its absence does not stop preflight or training, and its content is never used for training, tuning, early stopping, threshold selection, or model selection.
4. YOLO26s and BPD-YOLOn/L-FPN create a Colab-safe runtime `data.yaml` with resolved absolute POSIX paths instead of trusting stale Windows paths.
5. YOLO-style resume now loads the persistent `last.pt` checkpoint and resumes the existing run correctly.
6. RT-DETR-R18 uses the dedicated RT-DETR processor/model classes, safe AMP handling, visible progress, and persistent epoch checkpoints.
7. BPD-YOLOn/L-FPN custom DySample uses explicitly initialized convolutions instead of lazy parameters so the model parser can count parameters safely.
8. Preflight audits person-only COCO structure, actual image paths, YOLO label syntax/ranges, and train/validation group leakage.

## Validation performed

- Python source compilation passed for all three standalone engines.
- Notebook format validation passed for all three notebooks.
- All notebooks contain zero stale output/exception cells.
- The full training engine embedded in each notebook is byte-for-byte identical to its standalone `.py` file.
- Notebook Python cells passed static syntax checks, excluding Colab magics and `%%writefile` cells.
- Synthetic Step-2 dry-run passed for all three models with no private Final Test.
- Synthetic dry-run passed for all three models while deliberately supplying the exact stale placeholder:
  `/path/to/your/03_development_directory`
- `PROJECT_ROOT=AUTO` and `DEVELOPMENT_ROOT=AUTO` discovery passed for all three.
- YOLO26s/BPD label audits passed on the synthetic Step-2 structure.
- RT-DETR train/validation COCO and image-path audits passed on the synthetic Step-2 structure.

## Scope note

A complete 45-epoch NVIDIA L4 run against the user's actual Google Drive dataset cannot be executed in this offline validation environment. The package therefore should not be described as mathematically guaranteed to be error-free for every possible dataset or Colab state. It does, however, remove the reported path failure and the additional code-level issues found during review, and it passes the static and synthetic tests above.
