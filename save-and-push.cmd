@echo off
setlocal EnableExtensions EnableDelayedExpansion
title Aerial Human Detection - SAVE AND PUSH

set "REPO=D:\A_Senior - Data Science\Projects\aerial-human-detection"
set "SAFE_REPO=D:/A_Senior - Data Science/Projects/aerial-human-detection"
set "LOCK=%REPO%\.git\team-sync.lock"
set "LOG=%~dp0push-project.log"
set "RESULT=1"

cls
echo ============================================================
echo  Aerial Human Detection - SAVE AND PUSH
echo ============================================================
echo.
echo Repository:
echo %REPO%
echo.

call :MAIN
set "RESULT=%ERRORLEVEL%"

echo.
if "%RESULT%"=="0" (
    echo ============================================================
    echo  CHANGES SAVED AND PUSHED SUCCESSFULLY
    echo ============================================================
) else (
    echo ============================================================
    echo  PUSH FAILED - ERROR CODE %RESULT%
    echo ============================================================
)

echo.
echo A copy of this output is saved in:
echo %LOG%
echo.
pause
exit /b %RESULT%


:MAIN
call :RUN > "%LOG%" 2>&1
set "RC=%ERRORLEVEL%"
type "%LOG%"
exit /b %RC%


:RUN
echo Started: %DATE% %TIME%
echo User: %USERDOMAIN%\%USERNAME%
echo Computer: %COMPUTERNAME%
echo.

where git >nul 2>&1
if errorlevel 1 (
    echo ERROR: Git is not installed or is not available in PATH.
    exit /b 30
)

if not exist "%REPO%\" (
    echo ERROR: Repository folder was not found:
    echo %REPO%
    exit /b 31
)

if not exist "%REPO%\.git\" (
    echo ERROR: The folder is not a Git repository:
    echo %REPO%
    exit /b 32
)

cd /d "%REPO%"
if errorlevel 1 (
    echo ERROR: Could not enter the repository folder.
    exit /b 33
)

git config --global --get-all safe.directory 2>nul | findstr /x /c:"%SAFE_REPO%" >nul
if errorlevel 1 (
    git config --global --add safe.directory "%SAFE_REPO%"
    if errorlevel 1 (
        echo ERROR: Could not register this repository as safe.directory.
        exit /b 34
    )
)

mkdir "%LOCK%" 2>nul
if errorlevel 1 (
    echo ERROR: Another update or push operation may already be running.
    echo.
    echo Lock folder:
    echo %LOCK%
    echo.
    echo If nobody is using the scripts, delete that lock folder manually.
    exit /b 35
)

echo Lock acquired.
echo.

set "CONFLICTS="
for /f "delims=" %%F in ('git diff --name-only --diff-filter^=U') do set "CONFLICTS=1"

if defined CONFLICTS (
    echo ERROR: The repository has unresolved merge conflicts.
    echo.
    git status --short
    echo.
    echo Resolve the conflicts before running SAVE AND PUSH.
    rmdir "%LOCK%" >nul 2>&1
    exit /b 36
)

echo [1/8] Switching to main
git switch main
if errorlevel 1 (
    echo ERROR: Could not switch to main.
    rmdir "%LOCK%" >nul 2>&1
    exit /b 37
)
echo.

echo [2/8] Checking Git identity
for /f "delims=" %%A in ('git config --get user.name') do set "GIT_NAME=%%A"
for /f "delims=" %%A in ('git config --get user.email') do set "GIT_EMAIL=%%A"

if not defined GIT_NAME (
    echo ERROR: Git user.name is not configured for this Windows account.
    echo Run once:
    echo git config --global user.name "Your Name"
    rmdir "%LOCK%" >nul 2>&1
    exit /b 38
)

if not defined GIT_EMAIL (
    echo ERROR: Git user.email is not configured for this Windows account.
    echo Run once:
    echo git config --global user.email "your-github-email@example.com"
    rmdir "%LOCK%" >nul 2>&1
    exit /b 39
)

echo Commit author: !GIT_NAME! ^<!GIT_EMAIL!^>
echo.

echo [3/8] Fetching the latest origin/main
git fetch origin main
if errorlevel 1 (
    echo ERROR: Could not fetch origin/main.
    rmdir "%LOCK%" >nul 2>&1
    exit /b 40
)
echo.

echo [4/8] Staging all project changes
git add -A
if errorlevel 1 (
    echo ERROR: git add failed.
    rmdir "%LOCK%" >nul 2>&1
    exit /b 41
)
echo.

git diff --cached --quiet
if not errorlevel 1 (
    echo No new local changes were found.
    echo The script will only update the local branch.
    echo.
) else (
    echo [5/8] Creating a commit
    git commit -m "team-sync(%USERNAME%): %DATE% %TIME%"
    if errorlevel 1 (
        echo ERROR: Commit creation failed.
        rmdir "%LOCK%" >nul 2>&1
        exit /b 42
    )
    echo.
)

echo [6/8] Rebasing local main onto the latest origin/main
git pull --rebase origin main
if errorlevel 1 (
    echo ERROR: Rebase failed or produced conflicts.
    echo.
    echo Do not run the scripts again until conflicts are resolved.
    echo Use git status to inspect the problem.
    rmdir "%LOCK%" >nul 2>&1
    exit /b 43
)
echo.

echo [7/8] Pushing main to the central repository
git push origin main
if errorlevel 1 (
    echo First push attempt failed. Retrying after one fetch and rebase...
    git fetch origin main
    if errorlevel 1 (
        rmdir "%LOCK%" >nul 2>&1
        exit /b 44
    )

    git rebase origin/main
    if errorlevel 1 (
        echo ERROR: Retry rebase produced conflicts.
        rmdir "%LOCK%" >nul 2>&1
        exit /b 45
    )

    git push origin main
    if errorlevel 1 (
        echo ERROR: Push failed after retry.
        rmdir "%LOCK%" >nul 2>&1
        exit /b 46
    )
)
echo.

echo [8/8] Final repository status
git status --short --branch
echo.
echo Finished: %DATE% %TIME%

rmdir "%LOCK%" >nul 2>&1
exit /b 0
