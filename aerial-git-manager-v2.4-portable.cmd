@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul
title Aerial Human Detection - Git Manager V2

rem ============================================================
rem Aerial Human Detection - Shared Git Manager V2
rem One shared folder, one central remote, one main branch.
rem ============================================================

set "APP_NAME=Aerial Human Detection"
set "VERSION=2.4.0"

set "REMOTE=origin"
set "BRANCH=main"

set "APPDATA_DIR=%LOCALAPPDATA%\AerialHumanDetection\GitManagerCMDV2"
set "SETTINGS_FILE=%APPDATA_DIR%\repository-path.txt"
set "PROFILES_FILE=%APPDATA_DIR%\git-profiles.txt"
set "LOG_DIR=%APPDATA_DIR%\logs"

if not exist "%APPDATA_DIR%" mkdir "%APPDATA_DIR%" >nul 2>&1
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%" >nul 2>&1
if not exist "%PROFILES_FILE%" type nul > "%PROFILES_FILE%"

rem ANSI colors supported by modern Windows terminals.
for /F "delims=#" %%E in ('"prompt #$E# & for %%E in (1) do rem"') do set "ESC=%%E"
set "C_RESET=!ESC![0m"
set "C_BOLD=!ESC![1m"
set "C_DIM=!ESC![2m"
set "C_RED=!ESC![91m"
set "C_GREEN=!ESC![92m"
set "C_YELLOW=!ESC![93m"
set "C_BLUE=!ESC![94m"
set "C_MAGENTA=!ESC![95m"
set "C_CYAN=!ESC![96m"
set "C_WHITE=!ESC![97m"
set "C_GRAY=!ESC![90m"

call :RESOLVE_REPOSITORY
if errorlevel 1 (
    echo.
    pause
    exit /b 1
)

call :CHECK_ENVIRONMENT
if errorlevel 1 (
    echo.
    pause
    exit /b 1
)

:MAIN_MENU
cls
call :HEADER
call :LOAD_IDENTITY
call :SHOW_DASHBOARD

echo !C_BOLD!!C_WHITE!Main Menu!C_RESET!
echo.
echo   !C_CYAN![1]!C_RESET! Update project from GitHub
echo       Download the latest changes and preserve local edits.
echo.
echo   !C_GREEN![2]!C_RESET! Save, commit, and push changes
echo       Upload local work to the central main branch.
echo.
echo   !C_MAGENTA![3]!C_RESET! Full synchronization
echo       Update first, then save and push.
echo.
echo   !C_YELLOW![4]!C_RESET! Select or edit Git identity
echo       Choose the teammate name and GitHub email used for commits.
echo.
echo   !C_BLUE![5]!C_RESET! Repository status and diagnostics
echo.
echo   !C_BLUE![6]!C_RESET! Recent commits
echo.
echo   !C_BLUE![7]!C_RESET! Remotes and connection details
echo.
echo   !C_BLUE![8]!C_RESET! Open logs folder
echo.
echo   !C_BLUE![9]!C_RESET! Help and workflow guide
echo.
echo   !C_YELLOW![R]!C_RESET! Change repository path
echo.
echo   !C_RED![L]!C_RESET! Remove stale operation lock
echo   !C_GRAY![0]!C_RESET! Exit
echo.

set "MAIN_CHOICE="
set /p "MAIN_CHOICE=Select an option: "

if /i "!MAIN_CHOICE!"=="1" (
    call :UPDATE_PROJECT
    call :PAUSE_RETURN
    goto MAIN_MENU
)

if /i "!MAIN_CHOICE!"=="2" (
    call :SAVE_AND_PUSH
    call :PAUSE_RETURN
    goto MAIN_MENU
)

if /i "!MAIN_CHOICE!"=="3" (
    call :FULL_SYNC
    call :PAUSE_RETURN
    goto MAIN_MENU
)

if /i "!MAIN_CHOICE!"=="4" (
    call :IDENTITY_MENU
    goto MAIN_MENU
)

if /i "!MAIN_CHOICE!"=="5" (
    call :SHOW_STATUS
    call :PAUSE_RETURN
    goto MAIN_MENU
)

if /i "!MAIN_CHOICE!"=="6" (
    call :SHOW_HISTORY
    call :PAUSE_RETURN
    goto MAIN_MENU
)

if /i "!MAIN_CHOICE!"=="7" (
    call :SHOW_REMOTES
    call :PAUSE_RETURN
    goto MAIN_MENU
)

if /i "!MAIN_CHOICE!"=="8" (
    call :OPEN_LOGS
    goto MAIN_MENU
)

if /i "!MAIN_CHOICE!"=="9" (
    call :SHOW_HELP
    call :PAUSE_RETURN
    goto MAIN_MENU
)

if /i "!MAIN_CHOICE!"=="R" (
    call :CHANGE_REPOSITORY
    goto MAIN_MENU
)

if /i "!MAIN_CHOICE!"=="L" (
    call :REMOVE_STALE_LOCK
    call :PAUSE_RETURN
    goto MAIN_MENU
)

if /i "!MAIN_CHOICE!"=="0" exit /b 0

echo.
echo !C_RED!Invalid option.!C_RESET!
timeout /t 2 >nul
goto MAIN_MENU


rem ============================================================
rem Visual components
rem ============================================================

:HEADER
echo !C_CYAN!==============================================================================================================!C_RESET!
echo !C_BOLD!!C_WHITE!  %APP_NAME% - Team Git Manager V2!C_RESET!                         !C_GRAY!Version %VERSION%!C_RESET!
echo !C_CYAN!==============================================================================================================!C_RESET!
echo.
exit /b 0


:SHOW_DASHBOARD
set "CURRENT_BRANCH="
set "REMOTE_URL="
set "LOCAL_SHORT="
set "REMOTE_SHORT="
set "CHANGE_COUNT=0"
set "AHEAD_COUNT=0"
set "BEHIND_COUNT=0"

for /f "delims=" %%A in ('git -C "%REPO%" branch --show-current 2^>nul') do set "CURRENT_BRANCH=%%A"
for /f "delims=" %%A in ('git -C "%REPO%" remote get-url "%REMOTE%" 2^>nul') do set "REMOTE_URL=%%A"
for /f "delims=" %%A in ('git -C "%REPO%" rev-parse --short HEAD 2^>nul') do set "LOCAL_SHORT=%%A"
for /f "delims=" %%A in ('git -C "%REPO%" rev-parse --short "%REMOTE%/%BRANCH%" 2^>nul') do set "REMOTE_SHORT=%%A"
for /f %%A in ('git -C "%REPO%" status --porcelain 2^>nul ^| find /c /v ""') do set "CHANGE_COUNT=%%A"
for /f "tokens=1,2" %%A in ('git -C "%REPO%" rev-list --left-right --count "%REMOTE%/%BRANCH%...HEAD" 2^>nul') do (
    set "BEHIND_COUNT=%%A"
    set "AHEAD_COUNT=%%B"
)

echo !C_BOLD!Project Dashboard!C_RESET!
echo   Repository : %REPO%
echo   Branch     : !CURRENT_BRANCH!
echo   Remote     : !REMOTE_URL!
echo   Local HEAD : !LOCAL_SHORT!
echo   Remote HEAD: !REMOTE_SHORT!
echo   Changes    : !CHANGE_COUNT!
echo   Ahead      : !AHEAD_COUNT! commit(s)
echo   Behind     : !BEHIND_COUNT! commit(s)
echo   Identity   : !GIT_NAME! ^<!GIT_EMAIL!^>
echo.
exit /b 0


:PROGRESS
set /a "PCT=%~1"
set "PMSG=%~2"
set /a "FILLED=PCT/4"
set /a "EMPTY=25-FILLED"
set "PBAR="

for /L %%I in (1,1,!FILLED!) do set "PBAR=!PBAR!#"
for /L %%I in (1,1,!EMPTY!) do set "PBAR=!PBAR!-"

echo !C_CYAN![!PBAR!] !PCT!%%!C_RESET!  !PMSG!
exit /b 0


:STEP_OK
echo     !C_GREEN![OK]!C_RESET! %~1
exit /b 0


:STEP_INFO
echo     !C_BLUE![INFO]!C_RESET! %~1
exit /b 0


:STEP_WARN
echo     !C_YELLOW![WARN]!C_RESET! %~1
exit /b 0


:STEP_ERROR
echo     !C_RED![ERROR]!C_RESET! %~1
exit /b 0


rem ============================================================
rem Portable repository discovery
rem ============================================================

:RESOLVE_REPOSITORY
set "REPO="

rem 1. Path saved for this computer.
if exist "%SETTINGS_FILE%" (
    set "SAVED_REPO="
    set /p "SAVED_REPO="<"%SETTINGS_FILE%"
    call :TRY_REPOSITORY "!SAVED_REPO!"
    if defined REPO goto REPOSITORY_FOUND
)

rem 2. Folder containing this CMD file.
call :TRY_REPOSITORY "%~dp0"
if defined REPO goto REPOSITORY_FOUND

rem 3. Current command prompt directory.
call :TRY_REPOSITORY "%CD%"
if defined REPO goto REPOSITORY_FOUND

rem 4. Common locations.
call :TRY_REPOSITORY "%USERPROFILE%\Projects\aerial-human-detection"
if defined REPO goto REPOSITORY_FOUND

call :TRY_REPOSITORY "%USERPROFILE%\Documents\GitHub\aerial-human-detection"
if defined REPO goto REPOSITORY_FOUND

call :TRY_REPOSITORY "%USERPROFILE%\source\repos\aerial-human-detection"
if defined REPO goto REPOSITORY_FOUND

call :TRY_REPOSITORY "%USERPROFILE%\Desktop\aerial-human-detection"
if defined REPO goto REPOSITORY_FOUND

call :TRY_REPOSITORY "D:\A_Senior - Data Science\Projects\aerial-human-detection"
if defined REPO goto REPOSITORY_FOUND

:ASK_REPOSITORY
cls
call :HEADER
echo !C_YELLOW!The project repository was not found automatically.!C_RESET!
echo.
echo Paste the full path of the aerial-human-detection project.
echo You may paste the repository root or any folder inside it.
echo.
echo Example:
echo   D:\Projects\aerial-human-detection
echo.

set "ENTERED_REPO="
set /p "ENTERED_REPO=Project path: "

if not defined ENTERED_REPO (
    echo.
    echo The path cannot be empty.
    timeout /t 2 >nul
    goto ASK_REPOSITORY
)

call :TRY_REPOSITORY "!ENTERED_REPO!"

if not defined REPO (
    echo.
    echo !C_RED!The selected path is not inside a valid Git repository.!C_RESET!
    timeout /t 3 >nul
    goto ASK_REPOSITORY
)

:REPOSITORY_FOUND
> "%SETTINGS_FILE%" echo %REPO%
set "SAFE_REPO=%REPO:\=/%"
set "LOCK=%REPO%\.git\team-sync.lock"
exit /b 0


:TRY_REPOSITORY
set "CANDIDATE=%~1"
if not defined CANDIDATE exit /b 0
if not exist "%CANDIDATE%" exit /b 0

set "FOUND_ROOT="
for /f "delims=" %%A in ('git -C "%CANDIDATE%" rev-parse --show-toplevel 2^>nul') do set "FOUND_ROOT=%%A"

if defined FOUND_ROOT set "REPO=!FOUND_ROOT!"
exit /b 0


:CHANGE_REPOSITORY
cls
call :HEADER
echo !C_BOLD!Change repository path!C_RESET!
echo.
echo Current repository:
echo   %REPO%
echo.
echo Paste a new repository path, or press Enter to cancel.
echo.
set "NEW_REPOSITORY="
set /p "NEW_REPOSITORY=New project path: "

if not defined NEW_REPOSITORY exit /b 0

set "OLD_REPO=%REPO%"
set "REPO="
call :TRY_REPOSITORY "!NEW_REPOSITORY!"

if not defined REPO (
    set "REPO=!OLD_REPO!"
    echo.
    echo !C_RED!The selected path is not inside a valid Git repository.!C_RESET!
    call :PAUSE_RETURN
    exit /b 1
)

> "%SETTINGS_FILE%" echo !REPO!
set "SAFE_REPO=!REPO:\=/!"
set "LOCK=!REPO!\.git\team-sync.lock"

call :CHECK_ENVIRONMENT
if errorlevel 1 (
    set "REPO=!OLD_REPO!"
    set "SAFE_REPO=!REPO:\=/!"
    set "LOCK=!REPO!\.git\team-sync.lock"
    call :PAUSE_RETURN
    exit /b 1
)

echo.
echo !C_GREEN!Repository path updated successfully.!C_RESET!
echo   !REPO!
call :PAUSE_RETURN
exit /b 0


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
    echo ERROR: The configured folder is not a Git repository:
    echo %REPO%
    exit /b 1
)

cd /d "%REPO%"
if errorlevel 1 (
    echo ERROR: Could not open the repository folder.
    exit /b 1
)

git config --global --get-all safe.directory 2>nul | findstr /x /l /c:"%SAFE_REPO%" >nul
if errorlevel 1 (
    git config --global --add safe.directory "%SAFE_REPO%"
    if errorlevel 1 (
        echo ERROR: Could not register the repository as a safe Git directory.
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
rem Identity profiles
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

if not defined GIT_NAME set "GIT_NAME=[not configured]"
if not defined GIT_EMAIL set "GIT_EMAIL=[not configured]"
exit /b 0


:IDENTITY_MENU
:IDENTITY_MENU_LOOP
cls
call :HEADER
call :LOAD_IDENTITY

echo !C_BOLD!!C_WHITE!Git Identity Manager!C_RESET!
echo.
echo Current identity for this repository:
echo   Name : !GIT_NAME!
echo   Email: !GIT_EMAIL!
echo.
echo   !C_CYAN![1]!C_RESET! Continue with current identity
echo   !C_CYAN![2]!C_RESET! Select a saved teammate profile
echo   !C_CYAN![3]!C_RESET! Add and select a new profile
echo   !C_CYAN![4]!C_RESET! Edit current name and email
echo   !C_CYAN![5]!C_RESET! Edit current name only
echo   !C_CYAN![6]!C_RESET! Edit current email only
echo   !C_CYAN![7]!C_RESET! Save current identity as a profile
echo   !C_CYAN![8]!C_RESET! Delete a saved profile
echo   !C_CYAN![9]!C_RESET! List saved profiles
echo   !C_GRAY![0]!C_RESET! Return to main menu
echo.

set "IDENTITY_CHOICE="
set /p "IDENTITY_CHOICE=Select an option: "

if "!IDENTITY_CHOICE!"=="1" exit /b 0
if "!IDENTITY_CHOICE!"=="2" (
    call :SELECT_PROFILE
    goto IDENTITY_MENU_LOOP
)
if "!IDENTITY_CHOICE!"=="3" (
    call :ADD_PROFILE
    goto IDENTITY_MENU_LOOP
)
if "!IDENTITY_CHOICE!"=="4" (
    call :EDIT_BOTH
    goto IDENTITY_MENU_LOOP
)
if "!IDENTITY_CHOICE!"=="5" (
    call :EDIT_NAME
    goto IDENTITY_MENU_LOOP
)
if "!IDENTITY_CHOICE!"=="6" (
    call :EDIT_EMAIL
    goto IDENTITY_MENU_LOOP
)
if "!IDENTITY_CHOICE!"=="7" (
    call :SAVE_CURRENT_PROFILE
    goto IDENTITY_MENU_LOOP
)
if "!IDENTITY_CHOICE!"=="8" (
    call :DELETE_PROFILE
    goto IDENTITY_MENU_LOOP
)
if "!IDENTITY_CHOICE!"=="9" (
    call :LIST_PROFILES
    call :PAUSE_RETURN
    goto IDENTITY_MENU_LOOP
)
if "!IDENTITY_CHOICE!"=="0" exit /b 0

echo.
echo !C_RED!Invalid option.!C_RESET!
timeout /t 2 >nul
goto IDENTITY_MENU_LOOP


:ENSURE_IDENTITY_FOR_PUSH
call :LOAD_IDENTITY

if "!GIT_NAME!"=="[not configured]" (
    call :IDENTITY_MENU
    call :LOAD_IDENTITY
)

if "!GIT_EMAIL!"=="[not configured]" (
    call :IDENTITY_MENU
    call :LOAD_IDENTITY
)

if "!GIT_NAME!"=="[not configured]" exit /b 1
if "!GIT_EMAIL!"=="[not configured]" exit /b 1

:CONFIRM_IDENTITY_LOOP
cls
call :HEADER
echo !C_BOLD!Confirm Commit Identity!C_RESET!
echo.
echo The next commit will use:
echo.
echo   Name : !GIT_NAME!
echo   Email: !GIT_EMAIL!
echo.
echo   !C_GREEN![1]!C_RESET! Continue
echo   !C_YELLOW![2]!C_RESET! Select or edit identity
echo   !C_RED![0]!C_RESET! Cancel
echo.

set "CONFIRM_IDENTITY="
set /p "CONFIRM_IDENTITY=Select an option: "

if "!CONFIRM_IDENTITY!"=="1" exit /b 0
if "!CONFIRM_IDENTITY!"=="2" (
    call :IDENTITY_MENU
    call :LOAD_IDENTITY
    goto CONFIRM_IDENTITY_LOOP
)
if "!CONFIRM_IDENTITY!"=="0" exit /b 1

echo.
echo !C_RED!Invalid option.!C_RESET!
timeout /t 2 >nul
goto CONFIRM_IDENTITY_LOOP


:EDIT_BOTH
call :EDIT_NAME
if errorlevel 1 exit /b 1
call :EDIT_EMAIL
exit /b %ERRORLEVEL%


:EDIT_NAME
echo.
set "NEW_NAME="
set /p "NEW_NAME=Full name for Git commits: "

if not defined NEW_NAME (
    call :STEP_ERROR "Name cannot be empty."
    call :PAUSE_RETURN
    exit /b 1
)

git -C "%REPO%" config --local user.name "!NEW_NAME!"
if errorlevel 1 (
    call :STEP_ERROR "Could not save the Git user name."
    call :PAUSE_RETURN
    exit /b 1
)

set "GIT_NAME=!NEW_NAME!"
call :STEP_OK "Git user name updated."
call :PAUSE_RETURN
exit /b 0


:EDIT_EMAIL
echo.
set "NEW_EMAIL="
set /p "NEW_EMAIL=GitHub email for commits: "

if not defined NEW_EMAIL (
    call :STEP_ERROR "Email cannot be empty."
    call :PAUSE_RETURN
    exit /b 1
)

echo(!NEW_EMAIL!| findstr /r /c:"^[^@ ][^@ ]*@[^@ ][^@ ]*\.[^@ ][^@ ]*$" >nul
if errorlevel 1 (
    call :STEP_ERROR "Email format is not valid."
    call :PAUSE_RETURN
    exit /b 1
)

git -C "%REPO%" config --local user.email "!NEW_EMAIL!"
if errorlevel 1 (
    call :STEP_ERROR "Could not save the Git email."
    call :PAUSE_RETURN
    exit /b 1
)

set "GIT_EMAIL=!NEW_EMAIL!"
call :STEP_OK "Git email updated."
call :PAUSE_RETURN
exit /b 0


:ADD_PROFILE
cls
call :HEADER
echo !C_BOLD!Add Teammate Profile!C_RESET!
echo.

set "PROFILE_NAME="
set /p "PROFILE_NAME=Full name: "
if not defined PROFILE_NAME (
    call :STEP_ERROR "Name cannot be empty."
    call :PAUSE_RETURN
    exit /b 1
)

set "PROFILE_EMAIL="
set /p "PROFILE_EMAIL=GitHub email: "
if not defined PROFILE_EMAIL (
    call :STEP_ERROR "Email cannot be empty."
    call :PAUSE_RETURN
    exit /b 1
)

echo(!PROFILE_EMAIL!| findstr /r /c:"^[^@ ][^@ ]*@[^@ ][^@ ]*\.[^@ ][^@ ]*$" >nul
if errorlevel 1 (
    call :STEP_ERROR "Email format is not valid."
    call :PAUSE_RETURN
    exit /b 1
)

findstr /x /l /c:"!PROFILE_NAME!|!PROFILE_EMAIL!" "%PROFILES_FILE%" >nul 2>&1
if errorlevel 1 (
    >> "%PROFILES_FILE%" echo !PROFILE_NAME!^|!PROFILE_EMAIL!
)

git -C "%REPO%" config --local user.name "!PROFILE_NAME!"
git -C "%REPO%" config --local user.email "!PROFILE_EMAIL!"

call :STEP_OK "Profile saved and selected."
call :PAUSE_RETURN
exit /b 0


:SAVE_CURRENT_PROFILE
call :LOAD_IDENTITY

if "!GIT_NAME!"=="[not configured]" (
    call :STEP_ERROR "Current name is not configured."
    call :PAUSE_RETURN
    exit /b 1
)

if "!GIT_EMAIL!"=="[not configured]" (
    call :STEP_ERROR "Current email is not configured."
    call :PAUSE_RETURN
    exit /b 1
)

findstr /x /l /c:"!GIT_NAME!|!GIT_EMAIL!" "%PROFILES_FILE%" >nul 2>&1
if not errorlevel 1 (
    call :STEP_INFO "This profile is already saved."
    call :PAUSE_RETURN
    exit /b 0
)

>> "%PROFILES_FILE%" echo !GIT_NAME!^|!GIT_EMAIL!
call :STEP_OK "Current identity saved as a reusable profile."
call :PAUSE_RETURN
exit /b 0


:LIST_PROFILES
echo.
echo !C_BOLD!Saved teammate profiles!C_RESET!
echo.

set "PROFILE_COUNT=0"
for /f "tokens=1,* delims=:" %%N in ('findstr /n "^" "%PROFILES_FILE%" 2^>nul') do (
    set /a PROFILE_COUNT+=1
    for /f "tokens=1,* delims=|" %%A in ("%%O") do (
        echo   [%%N] %%A ^<%%B^>
    )
)

if "!PROFILE_COUNT!"=="0" echo   No saved profiles.
echo.
exit /b 0


:SELECT_PROFILE
cls
call :HEADER
call :LIST_PROFILES

if "!PROFILE_COUNT!"=="0" (
    call :PAUSE_RETURN
    exit /b 1
)

set "PROFILE_NUMBER="
set /p "PROFILE_NUMBER=Profile number: "

set "SELECTED_PROFILE="
for /f "tokens=1,* delims=:" %%N in ('findstr /n "^" "%PROFILES_FILE%"') do (
    if "%%N"=="!PROFILE_NUMBER!" set "SELECTED_PROFILE=%%O"
)

if not defined SELECTED_PROFILE (
    call :STEP_ERROR "Invalid profile number."
    call :PAUSE_RETURN
    exit /b 1
)

for /f "tokens=1,* delims=|" %%A in ("!SELECTED_PROFILE!") do (
    set "SELECTED_NAME=%%A"
    set "SELECTED_EMAIL=%%B"
)

git -C "%REPO%" config --local user.name "!SELECTED_NAME!"
git -C "%REPO%" config --local user.email "!SELECTED_EMAIL!"

call :STEP_OK "Selected !SELECTED_NAME! ^<!SELECTED_EMAIL!^>"
call :PAUSE_RETURN
exit /b 0


:DELETE_PROFILE
cls
call :HEADER
call :LIST_PROFILES

if "!PROFILE_COUNT!"=="0" (
    call :PAUSE_RETURN
    exit /b 1
)

set "DELETE_NUMBER="
set /p "DELETE_NUMBER=Profile number to delete: "

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
    call :STEP_ERROR "Invalid profile number."
    call :PAUSE_RETURN
    exit /b 1
)

move /y "!TEMP_PROFILES!" "%PROFILES_FILE%" >nul
call :STEP_OK "Profile deleted."
call :PAUSE_RETURN
exit /b 0


rem ============================================================
rem Lock and conflict handling
rem ============================================================

:ACQUIRE_LOCK
mkdir "%LOCK%" 2>nul
if errorlevel 1 (
    call :STEP_ERROR "Another update or push operation may already be running."
    echo.
    echo Lock folder:
    echo   %LOCK%
    echo.
    echo Use main menu option L only when nobody is using Git.
    exit /b 1
)

> "%LOCK%\owner.txt" (
    echo User=%USERDOMAIN%\%USERNAME%
    echo Computer=%COMPUTERNAME%
    echo Started=%DATE% %TIME%
)

exit /b 0


:RELEASE_LOCK
if exist "%LOCK%\" rmdir /s /q "%LOCK%" >nul 2>&1
exit /b 0


:CHECK_CONFLICTS
set "CONFLICTS="
for /f "delims=" %%F in ('git -C "%REPO%" diff --name-only --diff-filter^=U') do (
    set "CONFLICTS=1"
)

if defined CONFLICTS (
    call :STEP_ERROR "Unresolved merge conflicts were found."
    echo.
    git -C "%REPO%" status --short
    echo.
    echo Resolve the conflicts before continuing.
    exit /b 1
)

exit /b 0


:NEW_LOG
for /f %%T in ('powershell.exe -NoProfile -Command "Get-Date -Format yyyyMMdd-HHmmss"') do set "STAMP=%%T"
set "CURRENT_LOG=%LOG_DIR%\%~1-!STAMP!.log"
> "!CURRENT_LOG!" (
    echo %APP_NAME% - Git Manager V2
    echo Operation=%~1
    echo User=%USERDOMAIN%\%USERNAME%
    echo Computer=%COMPUTERNAME%
    echo Date=%DATE% %TIME%
    echo Repository=%REPO%
    echo.
)
exit /b 0


:LOG
>> "!CURRENT_LOG!" echo [%DATE% %TIME%] %*
exit /b 0


rem ============================================================
rem Update operation
rem ============================================================

:UPDATE_PROJECT
cls
call :HEADER
echo !C_BOLD!!C_CYAN!UPDATE PROJECT FROM GITHUB!C_RESET!
echo.
echo This operation downloads the latest remote changes.
echo Local uncommitted work is temporarily protected with Git stash.
echo.
call :PROGRESS 0 "Preparing update"

call :ACQUIRE_LOCK
if errorlevel 1 exit /b 1

call :CHECK_CONFLICTS
if errorlevel 1 (
    call :RELEASE_LOCK
    exit /b 1
)

call :NEW_LOG update
call :LOG "Update started"

set "STASH_CREATED=0"

call :PROGRESS 10 "Checking repository state"
git -C "%REPO%" status --short --branch
if errorlevel 1 (
    call :LOG "git status failed"
    call :RELEASE_LOCK
    exit /b 20
)
call :STEP_OK "Repository state checked."

set "HAS_CHANGES="
for /f "delims=" %%A in ('git -C "%REPO%" status --porcelain') do set "HAS_CHANGES=1"

call :PROGRESS 25 "Protecting local changes"
if defined HAS_CHANGES (
    git -C "%REPO%" stash push -u -m "Team auto-stash before update - %USERNAME% - %DATE% %TIME%"
    if errorlevel 1 (
        call :STEP_ERROR "Could not create a temporary stash."
        call :LOG "Stash creation failed"
        call :RELEASE_LOCK
        exit /b 21
    )
    set "STASH_CREATED=1"
    call :STEP_OK "Local changes saved temporarily."
) else (
    call :STEP_INFO "No local changes needed protection."
)

call :PROGRESS 40 "Switching to the shared main branch"
git -C "%REPO%" switch "%BRANCH%"
if errorlevel 1 (
    call :STEP_ERROR "Could not switch to %BRANCH%."
    call :LOG "Branch switch failed"
    call :RELEASE_LOCK
    exit /b 22
)
call :STEP_OK "Branch %BRANCH% is active."

call :PROGRESS 55 "Downloading remote objects"
echo.
echo !C_DIM!Git download progress appears below. Small updates may finish without a percentage display.!C_RESET!
echo.
git -C "%REPO%" fetch --progress "%REMOTE%" "%BRANCH%"
if errorlevel 1 (
    call :STEP_ERROR "Download from GitHub failed."
    if "!STASH_CREATED!"=="1" call :STEP_WARN "Your local changes are safe in Git stash."
    call :LOG "Fetch failed"
    call :RELEASE_LOCK
    exit /b 23
)
call :STEP_OK "Remote data downloaded."

call :PROGRESS 75 "Applying downloaded changes"
git -C "%REPO%" merge --ff-only "%REMOTE%/%BRANCH%"
if errorlevel 1 (
    call :STEP_ERROR "The local branch cannot be fast-forwarded."
    if "!STASH_CREATED!"=="1" call :STEP_WARN "Your local changes are safe in Git stash."
    call :LOG "Fast-forward merge failed"
    call :RELEASE_LOCK
    exit /b 24
)
call :STEP_OK "Latest project version applied."

call :PROGRESS 90 "Restoring local work"
if "!STASH_CREATED!"=="1" (
    git -C "%REPO%" stash pop
    if errorlevel 1 (
        call :STEP_ERROR "The update succeeded, but restoring local work caused conflicts."
        call :LOG "Stash pop caused conflicts"
        call :RELEASE_LOCK
        exit /b 25
    )
    call :STEP_OK "Local changes restored."
) else (
    call :STEP_INFO "Nothing needed restoration."
)

call :PROGRESS 100 "Update completed"
call :LOG "Update completed successfully"

echo.
git -C "%REPO%" status --short --branch
echo.
echo !C_GREEN!!C_BOLD!Project updated successfully.!C_RESET!
echo Log: !CURRENT_LOG!

call :RELEASE_LOCK
exit /b 0


rem ============================================================
rem Save, commit and push operation
rem ============================================================

:SAVE_AND_PUSH
call :ENSURE_IDENTITY_FOR_PUSH
if errorlevel 1 (
    echo.
    call :STEP_WARN "Push cancelled."
    exit /b 1
)

cls
call :HEADER
echo !C_BOLD!!C_GREEN!SAVE, COMMIT, AND PUSH!C_RESET!
echo.
echo Commit identity:
echo   Name : !GIT_NAME!
echo   Email: !GIT_EMAIL!
echo.
echo This operation uploads local changes to %REMOTE%/%BRANCH%.
echo.
call :PROGRESS 0 "Preparing upload"

call :ACQUIRE_LOCK
if errorlevel 1 exit /b 1

call :CHECK_CONFLICTS
if errorlevel 1 (
    call :RELEASE_LOCK
    exit /b 1
)

call :NEW_LOG push
call :LOG "Push started as !GIT_NAME! <!GIT_EMAIL!>"

call :PROGRESS 10 "Opening the shared main branch"
git -C "%REPO%" switch "%BRANCH%"
if errorlevel 1 (
    call :STEP_ERROR "Could not switch to %BRANCH%."
    call :LOG "Branch switch failed"
    call :RELEASE_LOCK
    exit /b 40
)
call :STEP_OK "Branch %BRANCH% is active."

call :PROGRESS 20 "Reviewing local changes"
set "CHANGE_COUNT=0"
for /f %%A in ('git -C "%REPO%" status --porcelain ^| find /c /v ""') do set "CHANGE_COUNT=%%A"
call :STEP_INFO "!CHANGE_COUNT! changed file(s) detected."

call :PROGRESS 30 "Staging project changes"
git -C "%REPO%" add -A
if errorlevel 1 (
    call :STEP_ERROR "Could not stage project changes."
    call :LOG "git add failed"
    call :RELEASE_LOCK
    exit /b 41
)
call :STEP_OK "Changes staged."

git -C "%REPO%" diff --cached --quiet
if not errorlevel 1 (
    call :PROGRESS 45 "No new commit required"
    call :STEP_INFO "No new local changes were found."
) else (
    call :PROGRESS 45 "Creating a commit"
    echo.
    set "COMMIT_MESSAGE="
    set /p "COMMIT_MESSAGE=Commit message [Enter = automatic]: "

    if not defined COMMIT_MESSAGE (
        set "COMMIT_MESSAGE=team-sync(!GIT_NAME!): %DATE% %TIME%"
    )

    git -C "%REPO%" commit -m "!COMMIT_MESSAGE!"
    if errorlevel 1 (
        call :STEP_ERROR "Commit creation failed."
        call :LOG "Commit failed"
        call :RELEASE_LOCK
        exit /b 42
    )
    call :STEP_OK "Commit created: !COMMIT_MESSAGE!"
    call :LOG "Commit created: !COMMIT_MESSAGE!"
)

call :PROGRESS 55 "Checking GitHub for newer changes"
echo.
echo !C_DIM!Git download progress appears below when objects must be transferred.!C_RESET!
echo.
git -C "%REPO%" fetch --progress "%REMOTE%" "%BRANCH%"
if errorlevel 1 (
    call :STEP_ERROR "Could not download the latest remote state."
    call :LOG "Fetch before push failed"
    call :RELEASE_LOCK
    exit /b 43
)
call :STEP_OK "Remote state checked."

call :PROGRESS 68 "Rebasing local commits safely"
git -C "%REPO%" rebase "%REMOTE%/%BRANCH%"
if errorlevel 1 (
    call :STEP_ERROR "Rebase failed or produced conflicts."
    echo.
    echo Run "git status" to inspect the conflict.
    call :LOG "Rebase failed"
    call :RELEASE_LOCK
    exit /b 44
)
call :STEP_OK "Local commits are based on the latest remote version."

call :PROGRESS 78 "Uploading changes to GitHub"
echo.
echo !C_DIM!Git upload progress appears below: counting, compressing, writing objects, and transfer speed.!C_RESET!
echo.
git -C "%REPO%" push --progress "%REMOTE%" "%BRANCH%"
if errorlevel 1 (
    call :STEP_WARN "First upload attempt failed. Retrying once."

    git -C "%REPO%" fetch --progress "%REMOTE%" "%BRANCH%"
    if errorlevel 1 (
        call :STEP_ERROR "Retry download failed."
        call :LOG "Retry fetch failed"
        call :RELEASE_LOCK
        exit /b 45
    )

    git -C "%REPO%" rebase "%REMOTE%/%BRANCH%"
    if errorlevel 1 (
        call :STEP_ERROR "Retry rebase failed."
        call :LOG "Retry rebase failed"
        call :RELEASE_LOCK
        exit /b 46
    )

    git -C "%REPO%" push --progress "%REMOTE%" "%BRANCH%"
    if errorlevel 1 (
        call :STEP_ERROR "Upload failed after the retry."
        call :LOG "Push failed after retry"
        call :RELEASE_LOCK
        exit /b 47
    )
)
call :STEP_OK "Upload completed."

call :PROGRESS 92 "Verifying local and remote commit hashes"
git -C "%REPO%" fetch "%REMOTE%" "%BRANCH%" >nul 2>&1
if errorlevel 1 (
    call :STEP_ERROR "Could not verify the remote state."
    call :LOG "Verification fetch failed"
    call :RELEASE_LOCK
    exit /b 48
)

set "LOCAL_HEAD="
set "REMOTE_HEAD="
for /f "delims=" %%A in ('git -C "%REPO%" rev-parse HEAD') do set "LOCAL_HEAD=%%A"
for /f "delims=" %%A in ('git -C "%REPO%" rev-parse "%REMOTE%/%BRANCH%"') do set "REMOTE_HEAD=%%A"

if not "!LOCAL_HEAD!"=="!REMOTE_HEAD!" (
    call :STEP_ERROR "Local and remote commit hashes differ after upload."
    call :LOG "Hash verification failed"
    call :RELEASE_LOCK
    exit /b 49
)
call :STEP_OK "Synchronization verified."

call :PROGRESS 100 "Save and upload completed"
call :LOG "Push completed successfully at !LOCAL_HEAD!"

echo.
git -C "%REPO%" status --short --branch
echo.
echo !C_GREEN!!C_BOLD!Changes saved and uploaded successfully.!C_RESET!
echo Commit: !LOCAL_HEAD!
echo Log: !CURRENT_LOG!

call :RELEASE_LOCK
exit /b 0


rem ============================================================
rem Full synchronization
rem ============================================================

:FULL_SYNC
cls
call :HEADER
echo !C_BOLD!!C_MAGENTA!FULL SYNCHRONIZATION!C_RESET!
echo.
echo Step 1: Update the shared project.
echo Step 2: Save and upload local changes.
echo.
set "FULL_CONFIRM="
set /p "FULL_CONFIRM=Type YES to continue: "

if /i not "!FULL_CONFIRM!"=="YES" (
    call :STEP_WARN "Full synchronization cancelled."
    exit /b 1
)

call :UPDATE_PROJECT
if errorlevel 1 (
    call :STEP_ERROR "Full synchronization stopped during update."
    exit /b 1
)

call :SAVE_AND_PUSH
if errorlevel 1 (
    call :STEP_ERROR "Full synchronization stopped during upload."
    exit /b 1
)

echo.
echo !C_GREEN!!C_BOLD!Full synchronization completed successfully.!C_RESET!
exit /b 0


rem ============================================================
rem Diagnostics and help
rem ============================================================

:SHOW_STATUS
cls
call :HEADER
echo !C_BOLD!Repository Status and Diagnostics!C_RESET!
echo.
git -C "%REPO%" status
echo.
echo Local commit:
git -C "%REPO%" log -1 --pretty=format:"  %%h  %%ad  %%an  %%s" --date=local
echo.
echo.
echo Tracking:
git -C "%REPO%" branch -vv
echo.
exit /b %ERRORLEVEL%


:SHOW_HISTORY
cls
call :HEADER
echo !C_BOLD!Recent Commits!C_RESET!
echo.
git -C "%REPO%" log -15 --graph --decorate --date=short --pretty=format:"%%C(auto)%%h%%Creset  %%ad  %%an  %%s"
echo.
echo.
exit /b %ERRORLEVEL%


:SHOW_REMOTES
cls
call :HEADER
echo !C_BOLD!Git Remotes and Connection Details!C_RESET!
echo.
git -C "%REPO%" remote -v
echo.
echo Central branch:
echo   %REMOTE%/%BRANCH%
echo.
echo Current credential authentication is handled by Git Credential Manager.
echo Commit author identity is selected separately in menu option 4.
echo.
exit /b %ERRORLEVEL%


:OPEN_LOGS
if not exist "%LOG_DIR%\" mkdir "%LOG_DIR%" >nul 2>&1
start "" "%LOG_DIR%"
exit /b 0


:SHOW_HELP
cls
call :HEADER
echo !C_BOLD!Workflow Guide!C_RESET!
echo.
echo Recommended team workflow:
echo.
echo   1. Before editing files, choose "Update project from GitHub".
echo   2. Work on the project.
echo   3. Choose "Save, commit, and push changes".
echo   4. Confirm the correct teammate identity before the commit.
echo.
echo Progress indicators:
echo.
echo   - The blue percentage bar shows overall operation-stage progress.
echo   - During Git download, Git displays object receiving percentages when data is transferred.
echo   - During Git upload, Git displays counting, compression, writing, percentage, and transfer speed.
echo   - Very small updates may complete too quickly for Git to print a network percentage.
echo.
echo Shared-folder rule:
echo.
echo   Only one teammate should edit or run Git operations at a time.
echo   The lock folder blocks simultaneous update and push operations.
echo.
echo Repository path:
echo.
echo   Detected automatically and saved separately on each computer.
echo.
echo Logs:
echo.
echo   %LOG_DIR%
echo.
echo Identity profiles:
echo.
echo   %PROFILES_FILE%
echo.
exit /b 0


:REMOVE_STALE_LOCK
cls
call :HEADER
echo !C_BOLD!!C_RED!Remove Stale Operation Lock!C_RESET!
echo.

if not exist "%LOCK%\" (
    call :STEP_INFO "No operation lock exists."
    exit /b 0
)

echo Lock information:
if exist "%LOCK%\owner.txt" type "%LOCK%\owner.txt"
echo.
echo Delete this lock only when no update or push process is running.
echo.
set "DELETE_LOCK="
set /p "DELETE_LOCK=Type DELETE to remove the lock: "

if /i not "!DELETE_LOCK!"=="DELETE" (
    call :STEP_WARN "Lock removal cancelled."
    exit /b 1
)

rmdir /s /q "%LOCK%" >nul 2>&1
if errorlevel 1 (
    call :STEP_ERROR "Could not remove the lock."
    exit /b 1
)

call :STEP_OK "Stale lock removed."
exit /b 0


:PAUSE_RETURN
echo.
pause
exit /b 0
