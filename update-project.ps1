<#
.SYNOPSIS
    Automated project updater for Aerial Human Detection
.DESCRIPTION
    Updates local repository with latest changes from GitHub.
    Handles conflicts, stashes local changes, and provides status feedback.
.EXAMPLE
    .\update-project.ps1
.NOTES
    Author: AliReza Khatibi
    Project: Aerial Human Detection
#>

# ============================================
# 🚁 Aerial Human Detection - Auto Updater
# ============================================

# تنظیم رنگ‌ها برای خروجی زیباتر
$colors = @{
    Success = 'Green'
    Warning = 'Yellow'
    Error   = 'Red'
    Info    = 'Cyan'
    Header  = 'Magenta'
}

# ============================================
# توابع کمکی
# ============================================

function Write-Header {
    param([string]$Message)
    Write-Host "`n========================================" -ForegroundColor $colors.Header
    Write-Host "  $Message" -ForegroundColor $colors.Header
    Write-Host "========================================`n" -ForegroundColor $colors.Header
}

function Write-Success {
    param([string]$Message)
    Write-Host "✅ $Message" -ForegroundColor $colors.Success
}

function Write-Warning {
    param([string]$Message)
    Write-Host "⚠️  $Message" -ForegroundColor $colors.Warning
}

function Write-Error {
    param([string]$Message)
    Write-Host "❌ $Message" -ForegroundColor $colors.Error
}

function Write-Info {
    param([string]$Message)
    Write-Host "ℹ️  $Message" -ForegroundColor $colors.Info
}

function Write-Step {
    param([string]$Message)
    Write-Host "🔄 $Message..." -ForegroundColor $colors.Info
}

# ============================================
# بررسی پیش‌نیازها
# ============================================

function Test-Prerequisites {
    Write-Step "Checking prerequisites"
    
    # بررسی نصب بودن Git
    try {
        git --version | Out-Null
        Write-Success "Git is installed"
    } catch {
        Write-Error "Git is not installed! Please install Git first."
        Write-Info "Download from: https://git-scm.com/downloads"
        exit 1
    }
    
    # بررسی اینکه در مسیر پروژه هستیم
    if (!(Test-Path ".git")) {
        Write-Error "Not in a Git repository!"
        Write-Info "Please navigate to the project folder first:"
        Write-Host "  cd aerial-human-detection" -ForegroundColor White
        exit 1
    }
    
    Write-Success "In correct project directory"
}

# ============================================
# نمایش وضعیت فعلی
# ============================================

function Show-CurrentStatus {
    Write-Step "Fetching current status"
    
    # برنچ فعلی
    $currentBranch = git branch --show-current
    Write-Info "Current branch: $currentBranch"
    
    # نمایش فایل‌های تغییر کرده
    $changes = git status --porcelain
    if ($changes) {
        Write-Warning "You have uncommitted changes:"
        git status --short
        Write-Host ""
    } else {
        Write-Success "Working directory is clean"
    }
    
    return $currentBranch
}

# ============================================
# ذخیره موقت تغییرات (Stash)
# ============================================

function Save-LocalChanges {
    $hasChanges = git status --porcelain
    
    if ($hasChanges) {
        Write-Step "Saving your local changes temporarily"
        
        $stashName = "auto-stash-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
        git stash push -m $stashName
        
        if ($LASTEXITCODE -eq 0) {
            Write-Success "Local changes saved as: $stashName"
            return $true
        } else {
            Write-Error "Failed to save local changes"
            return $false
        }
    }
    
    return $false
}

# ============================================
# بازیابی تغییرات (Stash Pop)
# ============================================

function Restore-LocalChanges {
    param([bool]$wasStashed)
    
    if ($wasStashed) {
        Write-Step "Restoring your local changes"
        
        git stash pop
        
        if ($LASTEXITCODE -eq 0) {
            Write-Success "Local changes restored successfully"
        } else {
            Write-Error "Conflict while restoring changes!"
            Write-Warning "Your changes are still in stash. Check with: git stash list"
            Write-Info "To apply manually: git stash pop"
            Write-Info "If conflicts: resolve them manually"
        }
    }
}

# ============================================
# آپدیت از Remote
# ============================================

function Update-FromRemote {
    param([string]$branchName)
    
    Write-Step "Fetching latest updates from GitHub"
    git fetch origin
    
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Failed to fetch from remote. Check your internet connection."
        return $false
    }
    
    Write-Success "Fetched latest changes"
    
    # بررسی اینکه برنچ remote تغییرات جدید داره یا نه
    $behind = git rev-list HEAD..origin/$branchName --count
    $ahead = git rev-list origin/$branchName..HEAD --count
    
    if ($behind -eq 0 -and $ahead -eq 0) {
        Write-Success "Your branch is already up to date!"
        return $true
    }
    
    if ($behind -gt 0) {
        Write-Info "Remote has $behind new commit(s)"
    }
    
    if ($ahead -gt 0) {
        Write-Warning "You have $ahead local commit(s) not yet pushed"
    }
    
    # Pull با rebase برای تاریخچه تمیزتر
    Write-Step "Pulling latest changes"
    git pull --rebase origin $branchName
    
    if ($LASTEXITCODE -eq 0) {
        Write-Success "Project updated successfully!"
        return $true
    } else {
        Write-Error "Pull failed! Possible merge conflict."
        return $false
    }
}

# ============================================
# مدیریت Conflict
# ============================================

function Handle-Conflict {
    Write-Warning "Merge conflicts detected!"
    Write-Host ""
    Write-Info "Files with conflicts:"
    git diff --name-only --diff-filter=U
    Write-Host ""
    
    # منوی انتخاب
    Write-Host "Choose an option:" -ForegroundColor White
    Write-Host "  [A] Abort update (keep everything as before)" -ForegroundColor White
    Write-Host "  [R] Resolve manually (open VS Code)" -ForegroundColor White
    Write-Host "  [S] Skip conflicted files (keep remote version)" -ForegroundColor White
    Write-Host "  [L] Keep local version for all conflicts" -ForegroundColor White
    Write-Host ""
    
    $choice = Read-Host "Your choice (A/R/S/L)"
    
    switch ($choice.ToUpper()) {
        "A" {
            Write-Step "Aborting update"
            git rebase --abort
            Write-Success "Update aborted. Everything is back to previous state."
        }
        "R" {
            Write-Step "Opening VS Code for manual resolution"
            code .
            Write-Info "Resolve conflicts in VS Code, then run:"
            Write-Host "  git add ." -ForegroundColor Cyan
            Write-Host "  git rebase --continue" -ForegroundColor Cyan
            Write-Host "  git push origin <branch-name>" -ForegroundColor Cyan
        }
        "S" {
            Write-Step "Accepting remote version for conflicts"
            $conflictedFiles = git diff --name-only --diff-filter=U
            foreach ($file in $conflictedFiles) {
                git checkout --theirs $file
                git add $file
                Write-Info "Accepted remote version: $file"
            }
            git rebase --continue
            Write-Success "Conflicts resolved with remote versions"
        }
        "L" {
            Write-Step "Keeping local version for conflicts"
            $conflictedFiles = git diff --name-only --diff-filter=U
            foreach ($file in $conflictedFiles) {
                git checkout --ours $file
                git add $file
                Write-Info "Kept local version: $file"
            }
            git rebase --continue
            Write-Success "Conflicts resolved with local versions"
        }
        default {
            Write-Warning "Invalid choice. Aborting update."
            git rebase --abort
        }
    }
}

# ============================================
# نمایش خلاصه تغییرات
# ============================================

function Show-UpdateSummary {
    Write-Step "Generating update summary"
    
    # نمایش آخرین commit ها
    Write-Host ""
    Write-Info "Recent commits (last 5):"
    git log --oneline -5 --pretty=format:"  %C(yellow)%h%Creset - %s %C(blue)(%an, %ar)%Creset"
    Write-Host ""
    
    # نمایش فایل‌های تغییر کرده در آخرین pull
    Write-Info "Files changed in last update:"
    git diff --stat HEAD@{1} HEAD 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Info "No changes to show (first pull or clean state)"
    }
}

# ============================================
# منوی اصلی
# ============================================

function Show-MainMenu {
    Write-Header "Aerial Human Detection - Updater"
    
    Write-Host "Select update mode:" -ForegroundColor White
    Write-Host "  [1] Quick update (pull latest changes)" -ForegroundColor White
    Write-Host "  [2] Full update (stash → pull → restore)" -ForegroundColor White
    Write-Host "  [3] Update from specific branch" -ForegroundColor White
    Write-Host "  [4] Check status only" -ForegroundColor White
    Write-Host "  [5] Push your changes first, then update" -ForegroundColor White
    Write-Host "  [Q] Quit" -ForegroundColor White
    Write-Host ""
    
    return Read-Host "Your choice"
}

# ============================================
# اجرای اصلی
# ============================================

function Main {
    Clear-Host
    
    # بررسی پیش‌نیازها
    Test-Prerequisites
    
    # نمایش وضعیت فعلی
    $currentBranch = Show-CurrentStatus
    
    # منوی اصلی
    $choice = Show-MainMenu
    
    switch ($choice) {
        "1" {
            # Quick Update
            Write-Header "Quick Update"
            
            if ($currentBranch -ne "main" -and $currentBranch -ne "develop") {
                Write-Warning "You are on branch '$currentBranch', not main/develop"
                $confirm = Read-Host "Switch to main branch first? (Y/N)"
                if ($confirm -eq "Y") {
                    git checkout main
                    $currentBranch = "main"
                }
            }
            
            $stashed = Save-LocalChanges
            $success = Update-FromRemote $currentBranch
            
            if (!$success) {
                Handle-Conflict
            } else {
                Show-UpdateSummary
            }
            
            Restore-LocalChanges $stashed
        }
        
        "2" {
            # Full Update
            Write-Header "Full Update (Safe Mode)"
            
            # رفتن به main
            Write-Step "Switching to main branch"
            $stashed = Save-LocalChanges
            git checkout main
            $currentBranch = "main"
            
            $success = Update-FromRemote $currentBranch
            
            if (!$success) {
                Handle-Conflict
            } else {
                Show-UpdateSummary
            }
            
            Restore-LocalChanges $stashed
        }
        
        "3" {
            # Update from specific branch
            Write-Header "Update from Specific Branch"
            
            Write-Info "Available branches:"
            git branch -a
            Write-Host ""
            
            $targetBranch = Read-Host "Enter branch name (e.g., develop)"
            
            $stashed = Save-LocalChanges
            git checkout $targetBranch
            
            if ($LASTEXITCODE -ne 0) {
                Write-Error "Failed to switch to branch: $targetBranch"
                Restore-LocalChanges $stashed
                return
            }
            
            $success = Update-FromRemote $targetBranch
            
            if (!$success) {
                Handle-Conflict
            } else {
                Show-UpdateSummary
            }
            
            Restore-LocalChanges $stashed
        }
        
        "4" {
            # Status only
            Write-Header "Repository Status"
            
            Write-Info "Branch: $currentBranch"
            Write-Info "Remote:"
            git remote -v
            Write-Host ""
            
            Write-Info "Your commits (not pushed):"
            git log origin/$currentBranch..HEAD --oneline 2>$null
            if ($LASTEXITCODE -ne 0) {
                Write-Info "  No unpushed commits"
            }
            
            Write-Host ""
            Write-Info "Remote commits (not pulled):"
            git fetch origin --dry-run 2>&1 | Select-String "->" 
            
            Write-Host ""
            Write-Info "Modified files:"
            git status --short
        }
        
        "5" {
            # Push then update
            Write-Header "Push & Update"
            
            # Push تغییرات محلی
            Write-Step "Pushing your local changes"
            git push origin $currentBranch
            
            if ($LASTEXITCODE -ne 0) {
                Write-Error "Push failed! Try pulling first."
                return
            }
            
            Write-Success "Your changes pushed successfully"
            
            # حالا pull کن
            $success = Update-FromRemote $currentBranch
            
            if (!$success) {
                Handle-Conflict
            } else {
                Show-UpdateSummary
            }
        }
        
        "Q" {
            Write-Info "Goodbye! 👋"
            return
        }
        
        default {
            Write-Error "Invalid choice!"
            Main
        }
    }
    
    Write-Host ""
    Write-Success "Update process completed!"
    Write-Info "Current branch: $(git branch --show-current)"
    Write-Host ""
}

# ============================================
# اجرا
# ============================================

try {
    Main
} catch {
    Write-Error "An unexpected error occurred: $_"
    Write-Info "If you're stuck, try:"
    Write-Host "  git status" -ForegroundColor Cyan
    Write-Host "  git stash list" -ForegroundColor Cyan
    Write-Host "  git branch" -ForegroundColor Cyan
} finally {
    Write-Host "`n========================================" -ForegroundColor $colors.Header
    Write-Host "  Update Script Finished" -ForegroundColor $colors.Header
    Write-Host "========================================`n" -ForegroundColor $colors.Header
}