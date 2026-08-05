@echo off
setlocal EnableExtensions EnableDelayedExpansion
title Aerial Human Detection - UPDATE

set "REPO=D:\A_Senior - Data Science\Projects\aerial-human-detection"
set "SAFE_REPO=D:/A_Senior - Data Science/Projects/aerial-human-detection"
set "LOCK=%REPO%\.git\team-sync.lock"
set "LOG=%~dp0update-project.log"
set "RESULT=1"
set "STASH_CREATED=0"

cls
echo ============================================================
echo  Aerial Human Detection - UPDATE PROJECT
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
    echo  PROJECT UPDATED SUCCESSFULLY
    echo ============================================================
) else (
    echo ============================================================
    echo  UPDATE FAILED - ERROR CODE %RESULT%
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
    exit /b 10
)

if not exist "%REPO%\" (
    echo ERROR: Repository folder was not found:
    echo %REPO%
    exit /b 11
)

if not exist "%REPO%\.git\" (
    echo ERROR: The folder is not a Git repository:
    echo %REPO%
    exit /b 12
)

cd /d "%REPO%"
if errorlevel 1 (
    echo ERROR: Could not enter the repository folder.
    exit /b 13
)

git config --global --get-all safe.directory 2>nul | findstr /x /c:"%SAFE_REPO%" >nul
if errorlevel 1 (
    git config --global --add safe.directory "%SAFE_REPO%"
    if errorlevel 1 (
        echo ERROR: Could not register this repository as safe.directory.
        exit /b 14
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
    exit /b 15
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
    echo Resolve the conflicts before running UPDATE.
    rmdir "%LOCK%" >nul 2>&1
    exit /b 16
)

echo [1/6] Repository status
git status --short --branch
if errorlevel 1 (
    rmdir "%LOCK%" >nul 2>&1
    exit /b 17
)
echo.

set "HAS_CHANGES="
for /f "delims=" %%A in ('git status --porcelain') do set "HAS_CHANGES=1"

if defined HAS_CHANGES (
    echo [2/6] Saving local changes temporarily
    git stash push -u -m "Team auto-stash before update - %USERNAME% - %DATE% %TIME%"
    if errorlevel 1 (
        echo ERROR: Could not create a stash.
        rmdir "%LOCK%" >nul 2>&1
        exit /b 18
    )
    set "STASH_CREATED=1"
) else (
    echo [2/6] No local changes to save
)
echo.

echo [3/6] Switching to main
git switch main
if errorlevel 1 (
    echo ERROR: Could not switch to main.
    rmdir "%LOCK%" >nul 2>&1
    exit /b 19
)
echo.

echo [4/6] Fetching origin/main
git fetch origin main
if errorlevel 1 (
    echo ERROR: Could not fetch origin/main.
    if "!STASH_CREATED!"=="1" echo Local changes are safe in Git stash.
    rmdir "%LOCK%" >nul 2>&1
    exit /b 20
)
echo.

echo [5/6] Updating main with fast-forward only
git pull --ff-only origin main
if errorlevel 1 (
    echo ERROR: The local main branch cannot be fast-forwarded.
    echo A local commit may exist that is not on GitHub.
    if "!STASH_CREATED!"=="1" echo Local changes are safe in Git stash.
    rmdir "%LOCK%" >nul 2>&1
    exit /b 21
)
echo.

if "!STASH_CREATED!"=="1" (
    echo [6/6] Restoring local changes
    git stash pop
    if errorlevel 1 (
        echo ERROR: The project was updated, but restoring local changes caused conflicts.
        echo Run git status and resolve the conflicting files.
        rmdir "%LOCK%" >nul 2>&1
        exit /b 22
    )
) else (
    echo [6/6] Nothing to restore
)
echo.

echo Final status:
git status --short --branch
echo.
echo Finished: %DATE% %TIME%

rmdir "%LOCK%" >nul 2>&1
exit /b 0
