# اجرای git init
git init

# بررسی وضعیت فایل‌ها
git status

# اگر همه چیز خوب بود
try {
    git add .
    Write-Host "Files added successfully" -ForegroundColor Green
} catch {
    Write-Host "Error adding files: $_" -ForegroundColor Red
}

# commit
try {
    git commit -m "🎉 Initial project structure - Set up project directory structure - Add README, .gitignore, and configuration files - Create placeholder files for all modules - Add requirements and development dependencies - Configure CI/CD workflows and pre-commit hooks"
    Write-Host "Committed successfully" -ForegroundColor Green
} catch {
    Write-Host "Error committing: $_" -ForegroundColor Red
}

# push به main
try {
    git push -u origin main
    Write-Host "Pushed to GitHub successfully" -ForegroundColor Green
} catch {
    Write-Host "Error pushing to GitHub: $_" -ForegroundColor Red
}

# نگه داشتن پنجره (اجباری)
Write-Host "`nPress any key to continue..." -ForegroundColor Yellow
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")