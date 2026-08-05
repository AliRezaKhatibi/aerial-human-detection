@echo off
setlocal EnableExtensions EnableDelayedExpansion
title Aerial Human Detection - Team Git Manager

rem ============================================================
rem Shared project configuration
rem ============================================================

set "REPO=D:\A_Senior - Data Science\Projects\aerial-human-detection"
set "SAFE_REPO=D:/A_Senior - Data Science/Projects/aerial-human-detection"
set "BRANCH=main"
set "REMOTE=origin"
set "LOCK=%REPO%\.git\team-sync.lock"

set "APPDATA_DIR=%LOCALAPPDATA%\AerialHumanDetection"
set "PROFILES_FILE=%APPDATA_DIR%\git-profiles.txt"
set "LOG_DIR=%APPDATA_DIR%\logs"

if not exist "%APPDATA_DIR%" mkdir "%APPDATA_DIR%" >nul 2>&1
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%" >nul 2>&1
if not exist "%PROFILES_FILE%" type nul > "%PROFILES_FILE%"

call :CHECK_ENVIRONMENT
if errorlevel 1 (
    echo.
    pause
    exit /b 1
)

:MAIN_MENU
cls
echo ============================================================
echo  Aerial Human Detection - Team Git Manager
echo ============================================================
echo.
echo Repository:
echo   %REPO%
echo.
call :LOAD_IDENTITY
echo Current Git identity:
if defined GIT_NAME (
    echo   Name : !GIT_NAME!
) else (
    echo   Name : [not configured]
)
if defined GIT_EMAIL (
    echo   Email: !GIT_EMAIL!
) else (
    echo   Email: [not configured]
)
echo.
echo Choose an operation:
echo.
echo   [1] Update project from GitHub
echo   [2] Save, commit, and push changes
echo   [3] Select or edit Git user identity
echo   [4] Show repository status
echo   [5] Show Git remotes
echo   [6] Remove a stale sync lock
echo   [0] Exit
echo.

set "MAIN_CHOICE="
set /p "MAIN_CHOICE=Enter your choice: "

if "%MAIN_CHOICE%"=="1" (
    call :UPDATE_PROJECT
    call :WAIT_AND_RETURN
    goto MAIN_MENU
)

if "%MAIN_CHOICE%"=="2" (
    call :SAVE_AND_PUSH
    call :WAIT_AND_RETURN
    goto MAIN_MENU
)

if "%MAIN_CHOICE%"=="3" (
    call :IDENTITY_MENU
    goto MAIN_MENU
)

if "%MAIN_CHOICE%"=="4" (
    call :SHOW_STATUS
    call :WAIT_AND_RETURN
    goto MAIN_MENU
)

if "%MAIN_CHOICE%"=="5" (
    call :SHOW_REMOTES
    call :WAIT_AND_RETURN
    goto MAIN_MENU
)

if "%MAIN_CHOICE%"=="6" (
    call :REMOVE_STALE_LOCK
    call :WAIT_AND_RETURN
    goto MAIN_MENU
)

if "%MAIN_CHOICE%"=="0" exit /b 0

echo.
echo Invalid option.
timeout /t 2 >nul
goto MAIN_MENU


rem ============================================================
rem Environment checks
rem ============================================================

:CHECK_ENVIRONMENT
where git >nul 2>&1
if errorlevel 1 (
    echo ERROR: Git is not installed or is not available in PATH.
    exit /b 1
)

if not exist "%REPO%\" (
    echo ERROR: Repository folder was not found:
    echo %REPO%
    exit /b 1
)

if not exist "%REPO%\.git\" (
    echo ERROR: This folder is not a Git repository:
    echo %REPO%
    exit /b 1
)

cd /d "%REPO%"
if errorlevel 1 (
    echo ERROR: Could not enter the repository folder.
    exit /b 1
)

git config --global --get-all safe.directory 2>nul | findstr /x /c:"%SAFE_REPO%" >nul
if errorlevel 1 (
    git config --global --add safe.directory "%SAFE_REPO%"
    if errorlevel 1 (
        echo ERROR: Could not register this repository as a Git safe.directory.
        exit /b 1
    )
)

git remote get-url "%REMOTE%" >nul 2>&1
if errorlevel 1 (
    echo ERROR: The Git remote "%REMOTE%" is not configured.
    exit /b 1
)

exit /b 0


rem ============================================================
rem Identity management
rem Identity is stored locally in this shared repository.
rem Saved profiles are stored outside the repository.
rem ============================================================

:LOAD_IDENTITY
set "GIT_NAME="
set "GIT_EMAIL="

for /f "usebackq delims=" %%A in (`git -C "%REPO%" config --local --get user.name 2^>nul`) do (
    if not defined GIT_NAME set "GIT_NAME=%%A"
)

for /f "usebackq delims=" %%A in (`git -C "%REPO%" config --local --get user.email 2^>nul`) do (
    if not defined GIT_EMAIL set "GIT_EMAIL=%%A"
)

if not defined GIT_NAME (
    for /f "usebackq delims=" %%A in (`git config --global --get user.name 2^>nul`) do (
        if not defined GIT_NAME set "GIT_NAME=%%A"
    )
)

if not defined GIT_EMAIL (
    for /f "usebackq delims=" %%A in (`git config --global --get user.email 2^>nul`) do (
        if not defined GIT_EMAIL set "GIT_EMAIL=%%A"
    )
)

exit /b 0


:IDENTITY_MENU
:IDENTITY_MENU_LOOP
cls
call :LOAD_IDENTITY

echo ============================================================
echo  Git User Identity
echo ============================================================
echo.
echo Current identity for this shared repository:
echo.
if defined GIT_NAME (
    echo   Name : !GIT_NAME!
) else (
    echo   Name : [not configured]
)
if defined GIT_EMAIL (
    echo   Email: !GIT_EMAIL!
) else (
    echo   Email: [not configured]
)
echo.
echo Saved profiles file:
echo   %PROFILES_FILE%
echo.
echo Choose an option:
echo.
echo   [1] Use current identity and return
echo   [2] Select a saved profile
echo   [3] Add a new profile
echo   [4] Edit current name and email
echo   [5] Edit current name only
echo   [6] Edit current email only
echo   [7] Delete a saved profile
echo   [8] List saved profiles
echo   [0] Return to main menu
echo.

set "IDENTITY_CHOICE="
set /p "IDENTITY_CHOICE=Enter your choice: "

if "%IDENTITY_CHOICE%"=="1" exit /b 0
if "%IDENTITY_CHOICE%"=="2" (
    call :SELECT_PROFILE
    goto IDENTITY_MENU_LOOP
)
if "%IDENTITY_CHOICE%"=="3" (
    call :ADD_PROFILE
    goto IDENTITY_MENU_LOOP
)
if "%IDENTITY_CHOICE%"=="4" (
    call :EDIT_BOTH
    goto IDENTITY_MENU_LOOP
)
if "%IDENTITY_CHOICE%"=="5" (
    call :EDIT_NAME
    goto IDENTITY_MENU_LOOP
)
if "%IDENTITY_CHOICE%"=="6" (
    call :EDIT_EMAIL
    goto IDENTITY_MENU_LOOP
)
if "%IDENTITY_CHOICE%"=="7" (
    call :DELETE_PROFILE
    goto IDENTITY_MENU_LOOP
)
if "%IDENTITY_CHOICE%"=="8" (
    call :LIST_PROFILES
    call :WAIT_AND_RETURN
    goto IDENTITY_MENU_LOOP
)
if "%IDENTITY_CHOICE%"=="0" exit /b 0

echo.
echo Invalid option.
timeout /t 2 >nul
goto IDENTITY_MENU_LOOP


:ENSURE_IDENTITY_FOR_PUSH
call :LOAD_IDENTITY

if not defined GIT_NAME (
    echo.
    echo Git user name is not configured.
    call :IDENTITY_MENU
    call :LOAD_IDENTITY
)

if not defined GIT_EMAIL (
    echo.
    echo Git email is not configured.
    call :IDENTITY_MENU
    call :LOAD_IDENTITY
)

if not defined GIT_NAME exit /b 1
if not defined GIT_EMAIL exit /b 1

:CONFIRM_IDENTITY_LOOP
cls
echo ============================================================
echo  Confirm Commit Identity
echo ============================================================
echo.
echo The next commit will be created as:
echo.
echo   Name : !GIT_NAME!
echo   Email: !GIT_EMAIL!
echo.
echo   [1] Continue with this identity
echo   [2] Select or edit identity
echo   [0] Cancel push
echo.

set "CONFIRM_IDENTITY="
set /p "CONFIRM_IDENTITY=Enter your choice: "

if "%CONFIRM_IDENTITY%"=="1" exit /b 0
if "%CONFIRM_IDENTITY%"=="2" (
    call :IDENTITY_MENU
    call :LOAD_IDENTITY
    goto CONFIRM_IDENTITY_LOOP
)
if "%CONFIRM_IDENTITY%"=="0" exit /b 1

echo.
echo Invalid option.
timeout /t 2 >nul
goto CONFIRM_IDENTITY_LOOP


:EDIT_BOTH
call :EDIT_NAME
if errorlevel 1 exit /b 1
call :EDIT_EMAIL
exit /b %ERRORLEVEL%


:EDIT_NAME
echo.
echo Enter the full name that should appear on Git commits.
echo Example: Ali Reza Khatibi
echo.

:ASK_NAME
set "NEW_NAME="
set /p "NEW_NAME=Git user name: "

if not defined NEW_NAME (
    echo The name cannot be empty.
    goto ASK_NAME
)

git -C "%REPO%" config --local user.name "!NEW_NAME!"
if errorlevel 1 (
    echo ERROR: Could not save the Git user name.
    exit /b 1
)

set "GIT_NAME=!NEW_NAME!"
echo.
echo Git user name updated successfully.
exit /b 0


:EDIT_EMAIL
echo.
echo Enter the email address connected to the GitHub account.
echo Example: name@example.com
echo.

:ASK_EMAIL
set "NEW_EMAIL="
set /p "NEW_EMAIL=Git email: "

if not defined NEW_EMAIL (
    echo The email cannot be empty.
    goto ASK_EMAIL
)

echo(!NEW_EMAIL!| findstr /r /c:"^[^@ ][^@ ]*@[^@ ][^@ ]*\.[^@ ][^@ ]*$" >nul
if errorlevel 1 (
    echo The email format is not valid.
    goto ASK_EMAIL
)

git -C "%REPO%" config --local user.email "!NEW_EMAIL!"
if errorlevel 1 (
    echo ERROR: Could not save the Git email.
    exit /b 1
)

set "GIT_EMAIL=!NEW_EMAIL!"
echo.
echo Git email updated successfully.
exit /b 0


:ADD_PROFILE
echo.
echo Add a new reusable Git profile.
echo.

set "PROFILE_NAME="
set /p "PROFILE_NAME=Full name: "
if not defined PROFILE_NAME (
    echo Profile name cannot be empty.
    call :WAIT_AND_RETURN
    exit /b 1
)

set "PROFILE_EMAIL="
set /p "PROFILE_EMAIL=GitHub email: "
if not defined PROFILE_EMAIL (
    echo Profile email cannot be empty.
    call :WAIT_AND_RETURN
    exit /b 1
)

echo(!PROFILE_EMAIL!| findstr /r /c:"^[^@ ][^@ ]*@[^@ ][^@ ]*\.[^@ ][^@ ]*$" >nul
if errorlevel 1 (
    echo Invalid email format.
    call :WAIT_AND_RETURN
    exit /b 1
)

findstr /x /l /c:"!PROFILE_NAME!|!PROFILE_EMAIL!" "%PROFILES_FILE%" >nul 2>&1
if not errorlevel 1 (
    echo.
    echo This profile already exists.
    call :WAIT_AND_RETURN
    exit /b 0
)

>> "%PROFILES_FILE%" echo !PROFILE_NAME!^|!PROFILE_EMAIL!

git -C "%REPO%" config --local user.name "!PROFILE_NAME!"
git -C "%REPO%" config --local user.email "!PROFILE_EMAIL!"

echo.
echo Profile saved and selected successfully.
call :WAIT_AND_RETURN
exit /b 0


:LIST_PROFILES
echo.
echo Saved Git profiles:
echo.

set "PROFILE_COUNT=0"
for /f "tokens=1,* delims=:" %%N in ('findstr /n "^" "%PROFILES_FILE%" 2^>nul') do (
    set /a PROFILE_COUNT+=1
    echo   [%%N] %%O
)

if "!PROFILE_COUNT!"=="0" echo   No saved profiles.

echo.
exit /b 0


:SELECT_PROFILE
call :LIST_PROFILES

if "!PROFILE_COUNT!"=="0" (
    call :WAIT_AND_RETURN
    exit /b 1
)

set "PROFILE_NUMBER="
set /p "PROFILE_NUMBER=Enter the profile number: "

set "SELECTED_PROFILE="
for /f "tokens=1,* delims=:" %%N in ('findstr /n "^" "%PROFILES_FILE%"') do (
    if "%%N"=="!PROFILE_NUMBER!" set "SELECTED_PROFILE=%%O"
)

if not defined SELECTED_PROFILE (
    echo.
    echo Invalid profile number.
    call :WAIT_AND_RETURN
    exit /b 1
)

for /f "tokens=1,* delims=|" %%A in ("!SELECTED_PROFILE!") do (
    set "SELECTED_NAME=%%A"
    set "SELECTED_EMAIL=%%B"
)

git -C "%REPO%" config --local user.name "!SELECTED_NAME!"
if errorlevel 1 (
    echo ERROR: Could not set the selected user name.
    call :WAIT_AND_RETURN
    exit /b 1
)

git -C "%REPO%" config --local user.email "!SELECTED_EMAIL!"
if errorlevel 1 (
    echo ERROR: Could not set the selected email.
    call :WAIT_AND_RETURN
    exit /b 1
)

echo.
echo Selected profile:
echo   Name : !SELECTED_NAME!
echo   Email: !SELECTED_EMAIL!
call :WAIT_AND_RETURN
exit /b 0


:DELETE_PROFILE
call :LIST_PROFILES

if "!PROFILE_COUNT!"=="0" (
    call :WAIT_AND_RETURN
    exit /b 1
)

set "DELETE_NUMBER="
set /p "DELETE_NUMBER=Enter the profile number to delete: "

set "TEMP_PROFILES=%PROFILES_FILE%.tmp"
type nul > "!TEMP_PROFILES!"
set "PROFILE_FOUND=0"

for /f "tokens=1,* delims=:" %%N in ('findstr /n "^" "%PROFILES_FILE%"') do (
    if "%%N"=="!DELETE_NUMBER!" (
        set "PROFILE_FOUND=1"
    ) else (
        >> "!TEMP_PROFILES!" echo %%O
    )
)

if "!PROFILE_FOUND!"=="0" (
    del "!TEMP_PROFILES!" >nul 2>&1
    echo.
    echo Invalid profile number.
    call :WAIT_AND_RETURN
    exit /b 1
)

move /y "!TEMP_PROFILES!" "%PROFILES_FILE%" >nul
echo.
echo Profile deleted successfully.
call :WAIT_AND_RETURN
exit /b 0


rem ============================================================
rem Lock and conflict checks
rem ============================================================

:ACQUIRE_LOCK
mkdir "%LOCK%" 2>nul
if errorlevel 1 (
    echo ERROR: Another update or push operation may already be running.
    echo.
    echo Lock folder:
    echo   %LOCK%
    echo.
    echo Use menu option 6 only when nobody is running Git operations.
    exit /b 1
)
exit /b 0


:RELEASE_LOCK
if exist "%LOCK%\" rmdir "%LOCK%" >nul 2>&1
exit /b 0


:CHECK_CONFLICTS
set "CONFLICTS="
for /f "delims=" %%F in ('git -C "%REPO%" diff --name-only --diff-filter^=U') do (
    set "CONFLICTS=1"
)

if defined CONFLICTS (
    echo ERROR: The repository has unresolved merge conflicts.
    echo.
    git -C "%REPO%" status --short
    echo.
    echo Resolve the conflicts before updating or pushing.
    exit /b 1
)

exit /b 0


rem ============================================================
rem Update operation
rem ============================================================

:UPDATE_PROJECT
cls
echo ============================================================
echo  UPDATE PROJECT FROM GITHUB
echo ============================================================
echo.

call :ACQUIRE_LOCK
if errorlevel 1 exit /b 1

call :CHECK_CONFLICTS
if errorlevel 1 (
    call :RELEASE_LOCK
    exit /b 1
)

set "UPDATE_LOG=%LOG_DIR%\update-%DATE:~-4%-%DATE:~4,2%-%DATE:~7,2%-%TIME:~0,2%-%TIME:~3,2%-%TIME:~6,2%.log"
set "UPDATE_LOG=%UPDATE_LOG: =0%"

call :RUN_UPDATE > "!UPDATE_LOG!" 2>&1
set "UPDATE_RC=!ERRORLEVEL!"

type "!UPDATE_LOG!"

call :RELEASE_LOCK

echo.
if "!UPDATE_RC!"=="0" (
    echo ============================================================
    echo  PROJECT UPDATED SUCCESSFULLY
    echo ============================================================
) else (
    echo ============================================================
    echo  UPDATE FAILED - ERROR CODE !UPDATE_RC!
    echo ============================================================
)

echo.
echo Log:
echo   !UPDATE_LOG!
exit /b !UPDATE_RC!


:RUN_UPDATE
set "STASH_CREATED=0"

echo Started: %DATE% %TIME%
echo Windows user: %USERDOMAIN%\%USERNAME%
echo Computer: %COMPUTERNAME%
echo.

echo [1/6] Current status
git -C "%REPO%" status --short --branch
if errorlevel 1 exit /b 20
echo.

set "HAS_CHANGES="
for /f "delims=" %%A in ('git -C "%REPO%" status --porcelain') do set "HAS_CHANGES=1"

if defined HAS_CHANGES (
    echo [2/6] Saving local changes temporarily
    git -C "%REPO%" stash push -u -m "Team auto-stash before update - %USERNAME% - %DATE% %TIME%"
    if errorlevel 1 exit /b 21
    set "STASH_CREATED=1"
) else (
    echo [2/6] No local changes to save
)
echo.

echo [3/6] Switching to %BRANCH%
git -C "%REPO%" switch "%BRANCH%"
if errorlevel 1 exit /b 22
echo.

echo [4/6] Fetching %REMOTE%/%BRANCH%
git -C "%REPO%" fetch "%REMOTE%" "%BRANCH%"
if errorlevel 1 exit /b 23
echo.

echo [5/6] Updating with fast-forward only
git -C "%REPO%" pull --ff-only "%REMOTE%" "%BRANCH%"
if errorlevel 1 (
    if "!STASH_CREATED!"=="1" echo Local changes are safe in Git stash.
    exit /b 24
)
echo.

if "!STASH_CREATED!"=="1" (
    echo [6/6] Restoring local changes
    git -C "%REPO%" stash pop
    if errorlevel 1 (
        echo The project was updated, but restoring local changes caused conflicts.
        exit /b 25
    )
) else (
    echo [6/6] Nothing to restore
)
echo.

echo Final status:
git -C "%REPO%" status --short --branch
exit /b 0


rem ============================================================
rem Save, commit, rebase and push operation
rem ============================================================

:SAVE_AND_PUSH
call :ENSURE_IDENTITY_FOR_PUSH
if errorlevel 1 (
    echo.
    echo Push cancelled.
    exit /b 1
)

cls
echo ============================================================
echo  SAVE, COMMIT, AND PUSH
echo ============================================================
echo.
echo Commit identity:
echo   Name : !GIT_NAME!
echo   Email: !GIT_EMAIL!
echo.

call :ACQUIRE_LOCK
if errorlevel 1 exit /b 1

call :CHECK_CONFLICTS
if errorlevel 1 (
    call :RELEASE_LOCK
    exit /b 1
)

set "PUSH_LOG=%LOG_DIR%\push-%DATE:~-4%-%DATE:~4,2%-%DATE:~7,2%-%TIME:~0,2%-%TIME:~3,2%-%TIME:~6,2%.log"
set "PUSH_LOG=%PUSH_LOG: =0%"

call :RUN_PUSH > "!PUSH_LOG!" 2>&1
set "PUSH_RC=!ERRORLEVEL!"

type "!PUSH_LOG!"

call :RELEASE_LOCK

echo.
if "!PUSH_RC!"=="0" (
    echo ============================================================
    echo  CHANGES SAVED AND PUSHED SUCCESSFULLY
    echo ============================================================
) else (
    echo ============================================================
    echo  PUSH FAILED - ERROR CODE !PUSH_RC!
    echo ============================================================
)

echo.
echo Log:
echo   !PUSH_LOG!
exit /b !PUSH_RC!


:RUN_PUSH
echo Started: %DATE% %TIME%
echo Windows user: %USERDOMAIN%\%USERNAME%
echo Computer: %COMPUTERNAME%
echo Git name: !GIT_NAME!
echo Git email: !GIT_EMAIL!
echo.

echo [1/8] Switching to %BRANCH%
git -C "%REPO%" switch "%BRANCH%"
if errorlevel 1 exit /b 40
echo.

echo [2/8] Fetching the latest %REMOTE%/%BRANCH%
git -C "%REPO%" fetch "%REMOTE%" "%BRANCH%"
if errorlevel 1 exit /b 41
echo.

echo [3/8] Staging all project changes
git -C "%REPO%" add -A
if errorlevel 1 exit /b 42
echo.

git -C "%REPO%" diff --cached --quiet
if not errorlevel 1 (
    echo [4/8] No new local changes found
    echo No commit will be created.
) else (
    echo [4/8] Creating a commit
    echo.

    set "COMMIT_MESSAGE="
    set /p "COMMIT_MESSAGE=Commit message [press Enter for automatic message]: "

    if not defined COMMIT_MESSAGE (
        set "COMMIT_MESSAGE=team-sync(!GIT_NAME!): %DATE% %TIME%"
    )

    git -C "%REPO%" commit -m "!COMMIT_MESSAGE!"
    if errorlevel 1 exit /b 43
)
echo.

echo [5/8] Rebasing local %BRANCH% onto %REMOTE%/%BRANCH%
git -C "%REPO%" pull --rebase "%REMOTE%" "%BRANCH%"
if errorlevel 1 (
    echo Rebase failed or produced conflicts.
    echo Run git status and resolve the conflict before retrying.
    exit /b 44
)
echo.

echo [6/8] Pushing to %REMOTE%/%BRANCH%
git -C "%REPO%" push "%REMOTE%" "%BRANCH%"
if errorlevel 1 (
    echo First push attempt failed. Retrying once...

    git -C "%REPO%" fetch "%REMOTE%" "%BRANCH%"
    if errorlevel 1 exit /b 45

    git -C "%REPO%" rebase "%REMOTE%/%BRANCH%"
    if errorlevel 1 exit /b 46

    git -C "%REPO%" push "%REMOTE%" "%BRANCH%"
    if errorlevel 1 exit /b 47
)
echo.

echo [7/8] Verifying synchronization
git -C "%REPO%" fetch "%REMOTE%" "%BRANCH%"
if errorlevel 1 exit /b 48

for /f "delims=" %%A in ('git -C "%REPO%" rev-parse HEAD') do set "LOCAL_HEAD=%%A"
for /f "delims=" %%A in ('git -C "%REPO%" rev-parse "%REMOTE%/%BRANCH%"') do set "REMOTE_HEAD=%%A"

if not "!LOCAL_HEAD!"=="!REMOTE_HEAD!" (
    echo ERROR: Local and remote commit hashes are different after push.
    exit /b 49
)
echo Synchronization verified.
echo.

echo [8/8] Final repository status
git -C "%REPO%" status --short --branch
exit /b 0


rem ============================================================
rem Information and maintenance
rem ============================================================

:SHOW_STATUS
cls
echo ============================================================
echo  REPOSITORY STATUS
echo ============================================================
echo.
git -C "%REPO%" status
echo.
exit /b %ERRORLEVEL%


:SHOW_REMOTES
cls
echo ============================================================
echo  GIT REMOTES
echo ============================================================
echo.
git -C "%REPO%" remote -v
echo.
exit /b %ERRORLEVEL%


:REMOVE_STALE_LOCK
cls
echo ============================================================
echo  REMOVE STALE SYNC LOCK
echo ============================================================
echo.

if not exist "%LOCK%\" (
    echo No sync lock exists.
    exit /b 0
)

echo Lock folder:
echo   %LOCK%
echo.
echo Delete it only if nobody is updating or pushing.
echo.
set "DELETE_LOCK="
set /p "DELETE_LOCK=Type DELETE to remove the lock: "

if /i not "%DELETE_LOCK%"=="DELETE" (
    echo Lock removal cancelled.
    exit /b 1
)

rmdir "%LOCK%" >nul 2>&1
if errorlevel 1 (
    echo ERROR: Could not remove the lock.
    exit /b 1
)

echo Lock removed successfully.
exit /b 0


:WAIT_AND_RETURN
echo.
pause
exit /b 0
