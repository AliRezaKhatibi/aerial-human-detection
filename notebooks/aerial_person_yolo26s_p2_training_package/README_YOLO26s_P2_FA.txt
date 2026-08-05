بسته آموزش نهایی YOLO26s-P2

فایل اصلی:
aerial_person_yolo26s_p2_final_training.ipynb

روش اجرا:
1. فایل را در Google Drive آپلود و با Google Colab باز کنید.
2. Runtime را روی GPU قرار دهید.
3. سلول‌ها را از بالا به پایین اجرا کنید.
4. دیتاست باید در مسیرهای تعریف‌شده در CELL 3 موجود باشد.
5. خروجی‌ها در مسیر زیر ذخیره می‌شوند:
   /content/drive/MyDrive/aerial_person_yolo26s_p2_final

ساختار آموزش:
- Stage 1: 8 epoch, imgsz=960, P2 warm-up
- Stage 2: 32 epoch, imgsz=1280, hybrid/context
- Stage 3: 10 epoch, imgsz=1280, Mosaic off
- Total: 50 epochs

نکات:
- Ultralytics روی نسخه 8.4.114 قفل شده است.
- معماری رسمی yolo26-p2.yaml استفاده می‌شود.
- وزن‌های سازگار از yolo26s.pt منتقل می‌شوند.
- Test فقط در انتها اجرا می‌شود.
- TensorRT باید روی RTX 3070 مقصد ساخته شود.