# Step 3 — Google Colab L4 Notebooks

This package contains three standalone Google Colab notebooks for the three Step-3 detector architectures fixed in Step 1:

1. `01_YOLO26s_Step3_Colab_L4.ipynb`
2. `02_RTDETR_R18_Step3_Colab_L4.ipynb`
3. `03_BPD_YOLOn_LFPN_Step3_Colab_L4.ipynb`

Each notebook embeds its full Python training engine and can therefore be uploaded directly to Google Colab without separately uploading the `.py` file.

## Core project controls

- English-only source code, comments, messages, and generated report fields.
- Google Colab runtime with NVIDIA L4.
- Person-only training.
- Fixed-budget baseline: 45 epochs, 1280 input, seed 42.
- Step-2 Development Pool only for training and internal validation.
- The private >=1000-image Final Test is optional in Step 3 and is never used by training.
- Persistent Google Drive storage.
- Checkpoint after every epoch.
- Automatic resume after Colab disconnects.
- Final Step-3 report artifacts, metrics, timing, VRAM, hashes, failure analysis, and checkpoints saved to Drive.

## Recommended use

Upload one `.ipynb` file to Colab, enable an L4 GPU, and run cells from top to bottom.

The configuration cell defaults to:

`/content/drive/MyDrive/aerial_person_project`

Change this path if your Step-2 project is stored elsewhere.

Keep `RUN_PREFLIGHT=True`. Once the preflight passes, keep `RUN_TRAINING=True` to start or resume training.

If batch size 2 causes an L4 out-of-memory error, change `BATCH_SIZE=1` and use a new run name if the controlled protocol is being changed.

The private Final Test does not need to exist during Step 3.
