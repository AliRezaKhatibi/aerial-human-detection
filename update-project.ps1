# ============================================================
# Safe Git project updater
# ============================================================

param(
    [string]$RepoPath = $PSScriptRoot
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Invoke-GitCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments,

        [Parameter(Mandatory = $true)]
        [string]$Description
    )

    Write-Host ""
    Write-Host "▶ $Description" -ForegroundColor Cyan
    Write-Host "  git $($Arguments -join ' ')" -ForegroundColor DarkGray

    & git @Arguments

    if ($LASTEXITCODE -ne 0) {
        throw "Git command failed: git $($Arguments -join ' ')"
    }
}

try {
    Write-Host ""
    Write-Host "============================================" -ForegroundColor DarkCyan
    Write-Host " Aerial Human Detection - Project Updater" -ForegroundColor Cyan
    Write-Host "============================================" -ForegroundColor DarkCyan

    # Resolve the repository path.
    $RepoPath = (Resolve-Path $RepoPath).Path

    Write-Host ""
    Write-Host "Repository:" -ForegroundColor Gray
    Write-Host $RepoPath -ForegroundColor White

    # Always run Git inside the repository.
    Set-Location $RepoPath

    # Confirm that Git is installed.
    $gitCommand = Get-Command git -ErrorAction SilentlyContinue

    if ($null -eq $gitCommand) {
        throw "Git is not installed or is not available in PATH."
    }

    # Add only this repository to Git safe.directory.
    $SafePath = $RepoPath.Replace("\", "/")

    $ExistingSafeDirectories = @(
        git config --global --get-all safe.directory 2>$null
    )

    if ($ExistingSafeDirectories -notcontains $SafePath) {
        Write-Host ""
        Write-Host "Adding repository to Git safe.directory..." `
            -ForegroundColor Yellow

        git config --global --add safe.directory $SafePath

        if ($LASTEXITCODE -ne 0) {
            throw "Could not add the repository to safe.directory."
        }
    }

    # Confirm that the selected folder is a Git repository.
    git rev-parse --is-inside-work-tree *> $null

    if ($LASTEXITCODE -ne 0) {
        throw "The selected directory is not a Git repository: $RepoPath"
    }

    # Display current branch.
    $CurrentBranch = git branch --show-current

    if ($LASTEXITCODE -ne 0) {
        throw "Could not determine the current Git branch."
    }

    Write-Host ""
    Write-Host "Current branch: $CurrentBranch" -ForegroundColor Gray

    # Detect local modified and untracked files.
    $StatusOutput = git status --porcelain

    if ($LASTEXITCODE -ne 0) {
        throw "Could not read the repository status."
    }

    $HasLocalChanges = -not [string]::IsNullOrWhiteSpace(
        ($StatusOutput -join "`n")
    )

    $StashCreated = $false

    if ($HasLocalChanges) {
        $StashMessage = "Automatic stash before update $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"

        Invoke-GitCommand `
            -Arguments @(
                "stash",
                "push",
                "-u",
                "-m",
                $StashMessage
            ) `
            -Description "Saving local changes"

        $StashCreated = $true
    }
    else {
        Write-Host ""
        Write-Host "No local changes need to be stashed." `
            -ForegroundColor DarkGray
    }

    # Switch to the main branch.
    Invoke-GitCommand `
        -Arguments @("switch", "main") `
        -Description "Switching to main branch"

    # Pull without creating an unexpected merge commit.
    Invoke-GitCommand `
        -Arguments @(
            "pull",
            "--ff-only",
            "origin",
            "main"
        ) `
        -Description "Downloading the latest main branch"

    # Restore local changes only when this script created a stash.
    if ($StashCreated) {
        Write-Host ""
        Write-Host "▶ Restoring local changes" -ForegroundColor Cyan

        & git stash pop

        if ($LASTEXITCODE -ne 0) {
            Write-Host ""
            Write-Host "The update completed, but restoring the stash produced conflicts." `
                -ForegroundColor Yellow

            Write-Host "Run 'git status' and resolve the conflicting files." `
                -ForegroundColor Yellow

            throw "Stash restoration requires manual conflict resolution."
        }
    }

    Write-Host ""
    Write-Host "============================================" -ForegroundColor Green
    Write-Host " Project updated successfully." -ForegroundColor Green
    Write-Host "============================================" -ForegroundColor Green

    Write-Host ""
    git status --short --branch
}
catch {
    Write-Host ""
    Write-Host "============================================" -ForegroundColor Red
    Write-Host " Update failed" -ForegroundColor Red
    Write-Host "============================================" -ForegroundColor Red
    Write-Host ""
    Write-Host $_.Exception.Message -ForegroundColor Red
    Write-Host ""
    Write-Host "Repository: $RepoPath" -ForegroundColor DarkGray

    $global:LASTEXITCODE = 1
}
finally {
    Write-Host ""
    Read-Host "Press Enter to close this window"
}
