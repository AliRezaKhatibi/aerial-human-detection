# بررسی و تنظیم ریموت (فقط اگر HTTPS نبود)
$currentRemote = git remote get-url origin 2>$null
if ($currentRemote -like "git@github.com:*") {
    Write-Host "Changing remote from SSH to HTTPS..." -ForegroundColor Yellow
    git remote set-url origin https://github.com/alavitabarreza79/aerial-human-detection.git
    Write-Host "Remote changed successfully" -ForegroundColor Green
} elseif (-not $currentRemote) {
    Write-Host "Setting remote origin..." -ForegroundColor Yellow
    git remote add origin https://github.com/alavitabarreza79/aerial-human-detection.git
}

# اجرای git init (در صورت نیاز)
git init

# بررسی وضعیت
git status

# اضافه کردن فایل‌ها
try {
    git add .
    Write-Host "Files added successfully" -ForegroundColor Green
} catch {
    Write-Host "Error adding files: $_" -ForegroundColor Red
}

# commit
try {
    git commit -m "Initial project structure - Set up project directory structure - Add README, .gitignore, and configuration files - Create placeholder files for all modules - Add requirements and development dependencies - Configure CI/CD workflows and pre-commit hooks"
    Write-Host "Committed successfully" -ForegroundColor Green
} catch {
    Write-Host "Error committing: $_" -ForegroundColor Red
}

# push
try {
    git push -u origin main
    Write-Host "Pushed to GitHub successfully" -ForegroundColor Green
} catch {
    Write-Host "Error pushing to GitHub: $_" -ForegroundColor Red
}

# نگه داشتن پنجره
Write-Host "`nPress any key to continue..." -ForegroundColor Yellow
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")