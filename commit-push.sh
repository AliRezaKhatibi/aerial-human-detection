git init
# بررسی وضعیت
git status

# اگر همه چیز خوب بود
git add .
Write-Host "Files added successfully" -ForegroundColor Green

# commit
git commit -m "🎉 Initial project structure - Set up project directory structure - Add README, .gitignore, and configuration files - Create placeholder files for all modules - Add requirements and development dependencies - Configure CI/CD workflows and pre-commit hooks"
Write-Host "Committed successfully" -ForegroundColor Green

# push به main
git push -u origin main
Write-Host "Pushed to GitHub successfully" -ForegroundColor Green