# Step 3 — Colab L4 V5 STRICT FINAL

This package contains strict Google Colab notebooks for the three final Step-3 models:

1. YOLO26s
2. RT-DETR-R18
3. BPD-YOLOn/L-FPN

## Why V5 exists

V4 could finish with all notebook cells marked successful even when training was intentionally skipped
(for example when the active GPU was not L4). V5 removes silent-skip behavior.

## Strict guarantees implemented by the notebook

- `RUN_TRAINING=True` is required.
- Missing CUDA raises an error.
- Wrong GPU raises an error when `REQUIRE_L4=True`.
- Failed preflight raises an error.
- Child-process training output is unbuffered and visible.
- A zero return code alone is not accepted as proof of training.
- Persistent checkpoints/history are verified after the training process returns.
- Each model uses a new stable V5 run name to avoid accidentally inheriting a completed older run.
- `RESUME="auto"` still resumes the V5 run after a Colab disconnect.
- The private >=1000-image Final Test remains optional and is never used during Step 3.

## Default V5 run names

- `yolo26s_fixed_budget_v5`
- `rtdetr_r18_fixed_budget_v5`
- `bpd_yolon_lfpn_fixed_budget_v5`

Do not change a run name while resuming the same interrupted experiment.

## Starting a genuinely fresh run

Set:

`RESUME = "none"`

and choose a NEW `RUN_NAME`.

After the first checkpoint is created, restore:

`RESUME = "auto"`

for interruption-safe continuation.
