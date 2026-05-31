# فایل‌های __init__.py برای پکیج‌های پایتون
touch src/__init__.py
touch src/data/__init__.py
touch src/models/__init__.py
touch src/models/detection/__init__.py
touch src/models/tracking/__init__.py
touch src/training/__init__.py
touch src/evaluation/__init__.py
touch src/inference/__init__.py
touch src/gui/__init__.py
touch src/utils/__init__.py
touch tests/__init__.py

# فایل‌های .gitignore و README
touch .gitignore README.md LICENSE

# فایل‌های requirements
touch requirements/base.txt requirements/dev.txt requirements/gui.txt

# فایل‌های کانفیگ
touch configs/default.yaml configs/model_yolo.yaml configs/model_rcnn.yaml configs/inference.yaml

# اسکریپت‌ها
touch scripts/download_dataset.sh scripts/train.sh scripts/evaluate.sh scripts/run_gui.sh
chmod +x scripts/*.sh  # قابل اجرا کردن اسکریپت‌ها

# مستندات
touch docs/architecture.md docs/dataset.md docs/experiments.md docs/setup.md docs/user_guide.md

# گیت‌هاب
touch .github/ISSUE_TEMPLATE/bug_report.md
touch .github/ISSUE_TEMPLATE/feature_request.md
touch .github/ISSUE_TEMPLATE/model_experiment.md
touch .github/PULL_REQUEST_TEMPLATE.md
touch .github/workflows/lint.yml
touch .github/workflows/test.yml

# کدهای اصلی
touch src/data/dataset.py src/data/transforms.py src/data/dataloader.py
touch src/models/detection/yolo.py src/models/detection/faster_rcnn.py src/models/detection/ssd.py
touch src/models/tracking/deepsort.py src/models/tracking/bytetrack.py
touch src/models/common.py
touch src/training/trainer.py src/training/losses.py src/training/metrics.py
touch src/evaluation/evaluator.py src/evaluation/benchmark.py src/evaluation/visualizer.py
touch src/inference/predictor.py src/inference/video_processor.py
touch src/gui/main_window.py src/gui/widgets.py
touch src/utils/config.py src/utils/logger.py src/utils/visualizer.py