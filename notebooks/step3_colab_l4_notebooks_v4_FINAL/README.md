# Step 3 — Final Google Colab L4 Training Package

This package contains the final Step-3 training notebooks and standalone Python engines for the three architectures fixed by the final Step-1 report:

1. YOLO26s
2. RT-DETR-R18
3. BPD-YOLOn/L-FPN

## Main fixes in this final package

- No placeholder path is required.
- `AUTO` path discovery searches for the canonical Step-2 `03_development` directory.
- An invalid old placeholder such as `/path/to/your/03_development_directory` is ignored and automatic discovery is attempted.
- The private >=1000-image Final Test is optional in Step 3 and is never read for training/tuning.
- YOLO-based notebooks write a Colab-safe runtime data YAML from the discovered Development Pool, avoiding stale Windows drive-letter paths.
- Ultralytics resume follows the official flow: load `last.pt`, then `train(resume=True)`.
- Every-epoch persistent checkpoints are enabled.
- RT-DETR-R18 saves both `last.pt` and a unique `epoch_XXX.pt` after each completed epoch.
- RT-DETR-R18 includes a live tqdm epoch progress bar.
- RT-DETR autocast no longer masks training exceptions.
- BPD DySample uses a regular channel-aware Conv2d so Ultralytics can count parameters while parsing the YAML; the earlier LazyConv2d initialization hazard is removed.
- Preflight now checks actual COCO image resolution and YOLO label syntax, not only folder names.
- Notebook wrappers do not add a second traceback when preflight fails; they print diagnostics and skip training safely.

## Default controlled baseline

- GPU: NVIDIA L4
- Epochs: 45
- Image size: 1280
- Batch: 2
- Seed: 42
- AMP: enabled
- Final Test: not used
- Checkpointing: every completed epoch
- Persistent storage: Google Drive

## Recommended order

Run:
1. `01_YOLO26s_Step3_Colab_L4_FINAL.ipynb`
2. `02_RTDETR_R18_Step3_Colab_L4_FINAL.ipynb`
3. `03_BPD_YOLOn_LFPN_Step3_Colab_L4_FINAL.ipynb`

Run each notebook from the first cell downward. Do not manually enter a Development path unless auto-discovery finds more than one candidate and you intentionally want to override the selected one.

## Expected Step-2 data layout

The preferred structure is:

<project>/workspace/aerial-person-data/03_development/
    train/images/
    train/labels/
    val/images/
    val/labels/

The Step-2 data parent should also contain the exported COCO JSON files and a data manifest. The scripts recursively discover the standard report/export file names.

## Final Test policy

The private >=1000-image Final Test is intentionally not required for Step 3. Its absence does not block training. If `FREEZE.json` exists, only freeze metadata may be recorded; Final-Test images and annotations remain untouched.
