# پوشه‌های اصلی
mkdir -p .github/{ISSUE_TEMPLATE,workflows}

# پوشه‌های دیتا
mkdir -p data/{raw,processed/{train,val,test},annotations}

# نوتبوک‌ها
mkdir -p notebooks

# کد اصلی
mkdir -p src/{data,models/{detection,tracking},training,evaluation,inference,gui/resources,utils}

# تست‌ها
mkdir -p tests/{test_data,test_models,test_training,test_inference}

# کانفیگ و اسکریپت
mkdir -p configs scripts

# مستندات
mkdir -p docs/api

# نتایج (با gitignore مدیریت میشه)
mkdir -p results/{checkpoints,logs,predictions,reports}

# نیازمندی‌ها
mkdir -p requirements