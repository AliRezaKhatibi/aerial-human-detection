param(
    [ValidateSet("Gui", "Worker")]
    [string]$Mode = "Gui",

    [string]$RequestPath = ""
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"

# ============================================================
# Aerial Human Detection - Git Manager GUI V2
# Windows PowerShell 5.1 + WPF, with no extra installation.
# ============================================================

$AppName = "Aerial Human Detection"
$Version = "2.4.0"
$DefaultRepo = ""
$DefaultRemote = "origin"
$DefaultBranch = "main"

$AppDataRoot = Join-Path $env:LOCALAPPDATA "AerialHumanDetection\GitManagerGUIV2"
$ProfilesPath = Join-Path $AppDataRoot "profiles.json"
$LogsPath = Join-Path $AppDataRoot "logs"
$RuntimePath = Join-Path $AppDataRoot "runtime"
$SettingsPath = Join-Path $AppDataRoot "settings.json"

foreach ($path in @($AppDataRoot, $LogsPath, $RuntimePath)) {
    if (-not (Test-Path -LiteralPath $path)) {
        New-Item -ItemType Directory -Path $path -Force | Out-Null
    }
}

# ============================================================
# Worker helpers
# ============================================================

function Write-AtomicJson {
    param(
        [Parameter(Mandatory = $true)] [object]$Value,
        [Parameter(Mandatory = $true)] [string]$Path
    )

    $temporaryPath = "$Path.tmp"
    $Value | ConvertTo-Json -Depth 8 -Compress |
        Set-Content -LiteralPath $temporaryPath -Encoding UTF8

    Move-Item -LiteralPath $temporaryPath -Destination $Path -Force
}

function Write-WorkerLog {
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyString()]
        [string]$Message
    )

    # Native Git output can legitimately contain blank lines. Those lines
    # must never be treated as a PowerShell parameter-binding failure.
    if ([string]::IsNullOrEmpty($Message)) {
        [System.IO.File]::AppendAllText(
            $script:WorkerLogPath,
            [Environment]::NewLine,
            [System.Text.Encoding]::UTF8
        )
        return
    }

    $timestamp = Get-Date -Format "HH:mm:ss"
    $line = "[$timestamp] $Message"
    [System.IO.File]::AppendAllText(
        $script:WorkerLogPath,
        $line + [Environment]::NewLine,
        [System.Text.Encoding]::UTF8
    )
}

function Set-WorkerProgress {
    param(
        [Parameter(Mandatory = $true)] [int]$Percent,
        [Parameter(Mandatory = $true)] [string]$Status,
        [string]$Phase = ""
    )

    $safePercent = [Math]::Max(0, [Math]::Min(100, $Percent))

    Write-AtomicJson -Path $script:WorkerProgressPath -Value ([ordered]@{
        percent   = $safePercent
        status    = $Status
        phase     = $Phase
        updatedAt = (Get-Date).ToString("o")
    })
}

function Complete-Worker {
    param(
        [Parameter(Mandatory = $true)] [bool]$Success,
        [Parameter(Mandatory = $true)] [string]$Message,
        [int]$ExitCode = 0
    )

    Write-AtomicJson -Path $script:WorkerDonePath -Value ([ordered]@{
        success     = $Success
        message     = $Message
        exitCode    = $ExitCode
        completedAt = (Get-Date).ToString("o")
    })
}

function ConvertTo-NativeArgument {
    param([Parameter(Mandatory = $true)] [string]$Value)

    if ($Value -notmatch '[\s"]') {
        return $Value
    }

    return '"' + ($Value.Replace('\', '\\').Replace('"', '\"')) + '"'
}

function Invoke-GitCapture {
    param(
        [Parameter(Mandatory = $true)] [string[]]$Arguments,
        [switch]$AllowFailure
    )

    Write-WorkerLog ("git " + ($Arguments -join " "))

    # Git writes some successful informational messages to stderr.
    # Windows PowerShell 5.1 can turn those messages into terminating
    # errors when ErrorActionPreference is Stop. Temporarily use
    # Continue and decide success only from Git's real exit code.
    $previousErrorActionPreference = $ErrorActionPreference

    try {
        $ErrorActionPreference = "Continue"
        $output = @(& git -C $script:WorkerRepo @Arguments 2>&1)
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }

    foreach ($line in $output) {
        $textLine = [string]$line

        if ([string]::IsNullOrWhiteSpace($textLine)) {
            continue
        }

        Write-WorkerLog $textLine
    }

    if (($exitCode -ne 0) -and (-not $AllowFailure)) {
        $details = ($output | ForEach-Object { [string]$_ }) -join [Environment]::NewLine

        if ([string]::IsNullOrWhiteSpace($details)) {
            $details = "Git returned exit code $exitCode."
        }

        throw "Git command failed: git $($Arguments -join ' ')`r`n$details"
    }

    return [pscustomobject]@{
        ExitCode = $exitCode
        Output   = @($output | ForEach-Object { [string]$_ })
    }
}

function Invoke-GitAnimated {
    param(
        [Parameter(Mandatory = $true)] [string[]]$Arguments,
        [Parameter(Mandatory = $true)] [int]$StartPercent,
        [Parameter(Mandatory = $true)] [int]$EndPercent,
        [Parameter(Mandatory = $true)] [string]$Status,
        [Parameter(Mandatory = $true)] [string]$Phase
    )

    $argumentLine = ($Arguments | ForEach-Object {
        ConvertTo-NativeArgument $_
    }) -join " "

    Write-WorkerLog ("git " + ($Arguments -join " "))

    # Use System.Diagnostics.Process directly. Start-Process can occasionally
    # report a stale or incorrect ExitCode for very fast redirected Git
    # commands in Windows PowerShell 5.1.
    $startInfo = New-Object System.Diagnostics.ProcessStartInfo
    $startInfo.FileName = "git.exe"
    $startInfo.Arguments = $argumentLine
    $startInfo.WorkingDirectory = $script:WorkerRepo
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true

    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $startInfo

    if (-not $process.Start()) {
        throw "Could not start Git."
    }

    # Read both streams asynchronously to avoid output-buffer deadlocks.
    $stdoutTask = $process.StandardOutput.ReadToEndAsync()
    $stderrTask = $process.StandardError.ReadToEndAsync()

    $currentPercent = $StartPercent
    $maximumAnimatedPercent = [Math]::Max(
        $StartPercent,
        $EndPercent - 1
    )

    while (-not $process.WaitForExit(250)) {
        Set-WorkerProgress `
            -Percent $currentPercent `
            -Status $Status `
            -Phase $Phase

        if ($currentPercent -lt $maximumAnimatedPercent) {
            $currentPercent++
        }
    }

    # A second WaitForExit ensures asynchronous stream handlers are complete
    # before reading ExitCode and output.
    $process.WaitForExit()

    $stdout = [string]$stdoutTask.Result
    $stderr = [string]$stderrTask.Result
    $exitCode = [int]$process.ExitCode

    foreach ($content in @($stdout, $stderr)) {
        if (-not [string]::IsNullOrWhiteSpace($content)) {
            foreach ($line in ($content -split "\r?\n")) {
                if (-not [string]::IsNullOrWhiteSpace($line)) {
                    Write-WorkerLog $line
                }
            }
        }
    }

    if ($exitCode -ne 0) {
        $details = (@($stderr, $stdout) |
            Where-Object { -not [string]::IsNullOrWhiteSpace($_) }) -join "`r`n"

        if ([string]::IsNullOrWhiteSpace($details)) {
            $details = "Git returned exit code $exitCode without additional output."
        }

        throw "Git command failed: git $($Arguments -join ' ')`r`n$details"
    }

    Set-WorkerProgress `
        -Percent $EndPercent `
        -Status $Status `
        -Phase $Phase
}

function Convert-LocalProgress {
    param(
        [Parameter(Mandatory = $true)] [int]$LocalPercent,
        [Parameter(Mandatory = $true)] [int]$BasePercent,
        [Parameter(Mandatory = $true)] [int]$SpanPercent
    )

    return [int][Math]::Round(
        $BasePercent + (($LocalPercent / 100.0) * $SpanPercent)
    )
}

function Set-OperationProgress {
    param(
        [Parameter(Mandatory = $true)] [int]$LocalPercent,
        [Parameter(Mandatory = $true)] [int]$BasePercent,
        [Parameter(Mandatory = $true)] [int]$SpanPercent,
        [Parameter(Mandatory = $true)] [string]$Status,
        [string]$Phase = ""
    )

    $mapped = Convert-LocalProgress `
        -LocalPercent $LocalPercent `
        -BasePercent $BasePercent `
        -SpanPercent $SpanPercent

    Set-WorkerProgress -Percent $mapped -Status $Status -Phase $Phase
}

function Invoke-AnimatedOperationGit {
    param(
        [Parameter(Mandatory = $true)] [string[]]$Arguments,
        [Parameter(Mandatory = $true)] [int]$LocalStart,
        [Parameter(Mandatory = $true)] [int]$LocalEnd,
        [Parameter(Mandatory = $true)] [int]$BasePercent,
        [Parameter(Mandatory = $true)] [int]$SpanPercent,
        [Parameter(Mandatory = $true)] [string]$Status,
        [Parameter(Mandatory = $true)] [string]$Phase
    )

    $mappedStart = Convert-LocalProgress $LocalStart $BasePercent $SpanPercent
    $mappedEnd = Convert-LocalProgress $LocalEnd $BasePercent $SpanPercent

    Invoke-GitAnimated `
        -Arguments $Arguments `
        -StartPercent $mappedStart `
        -EndPercent $mappedEnd `
        -Status $Status `
        -Phase $Phase
}

function Test-WorkerEnvironment {
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        throw "Git is not installed or is not available in PATH."
    }

    if (-not (Test-Path -LiteralPath $script:WorkerRepo)) {
        throw "Repository folder was not found: $($script:WorkerRepo)"
    }

    $gitFolder = Join-Path $script:WorkerRepo ".git"
    if (-not (Test-Path -LiteralPath $gitFolder)) {
        throw "The selected folder is not a Git repository."
    }

    $safePath = $script:WorkerRepo.Replace("\", "/")
    $safeDirectories = @(& git config --global --get-all safe.directory 2>$null)

    if ($safeDirectories -notcontains $safePath) {
        & git config --global --add safe.directory $safePath
        if ($LASTEXITCODE -ne 0) {
            throw "The repository could not be added to Git safe.directory."
        }
    }

    $remoteCheck = Invoke-GitCapture `
        -Arguments @("remote", "get-url", $script:WorkerRemote) `
        -AllowFailure

    if ($remoteCheck.ExitCode -ne 0) {
        throw "Git remote '$($script:WorkerRemote)' is not configured."
    }
}

function Acquire-WorkerLock {
    $script:WorkerLockPath = Join-Path $script:WorkerRepo ".git\team-sync.lock"

    try {
        New-Item -ItemType Directory -Path $script:WorkerLockPath -ErrorAction Stop |
            Out-Null
    }
    catch {
        $ownerPath = Join-Path $script:WorkerLockPath "owner.txt"
        $ownerText = ""

        if (Test-Path -LiteralPath $ownerPath) {
            $ownerText = (Get-Content -LiteralPath $ownerPath -Raw -ErrorAction SilentlyContinue)
        }

        throw "Another Git operation may already be running.`n$ownerText"
    }

    @(
        "User=$env:USERDOMAIN\$env:USERNAME"
        "Computer=$env:COMPUTERNAME"
        "Started=$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
        "Operation=$($script:WorkerRequest.operation)"
    ) | Set-Content `
        -LiteralPath (Join-Path $script:WorkerLockPath "owner.txt") `
        -Encoding UTF8
}

function Release-WorkerLock {
    if ($script:WorkerLockPath -and (Test-Path -LiteralPath $script:WorkerLockPath)) {
        Remove-Item -LiteralPath $script:WorkerLockPath -Recurse -Force `
            -ErrorAction SilentlyContinue
    }
}

function Test-UnresolvedConflicts {
    $conflicts = @(& git -C $script:WorkerRepo diff --name-only --diff-filter=U 2>$null)

    if ($conflicts.Count -gt 0) {
        throw "Unresolved merge conflicts exist: $($conflicts -join ', ')"
    }
}

function Set-CommitIdentity {
    param(
        [string]$Name,
        [string]$Email
    )

    if (-not [string]::IsNullOrWhiteSpace($Name)) {
        Invoke-GitCapture -Arguments @("config", "--local", "user.name", $Name) |
            Out-Null
    }

    if (-not [string]::IsNullOrWhiteSpace($Email)) {
        Invoke-GitCapture -Arguments @("config", "--local", "user.email", $Email) |
            Out-Null
    }
}

function Invoke-UpdateWorker {
    param(
        [int]$BasePercent = 0,
        [int]$SpanPercent = 100
    )

    Write-WorkerLog "Starting update operation."

    Set-OperationProgress 5 $BasePercent $SpanPercent `
        "Checking repository state..." "Preflight"

    Invoke-GitCapture -Arguments @("status", "--short", "--branch") | Out-Null

    $statusOutput = @(& git -C $script:WorkerRepo status --porcelain)
    if ($LASTEXITCODE -ne 0) {
        throw "Could not read repository status."
    }

    $stashCreated = $false

    Set-OperationProgress 20 $BasePercent $SpanPercent `
        "Protecting local changes..." "Local changes"

    if ($statusOutput.Count -gt 0) {
        $stashMessage = "GUI V2 auto-stash before update - $env:USERNAME - $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"

        Invoke-GitCapture `
            -Arguments @("stash", "push", "-u", "-m", $stashMessage) |
            Out-Null

        $stashCreated = $true
        Write-WorkerLog "Local changes were stored temporarily."
    }
    else {
        Write-WorkerLog "No local changes required a temporary stash."
    }

    Set-OperationProgress 35 $BasePercent $SpanPercent `
        "Opening the shared main branch..." "Branch"

    Invoke-GitCapture -Arguments @("switch", "--quiet", $script:WorkerBranch) | Out-Null

    Invoke-AnimatedOperationGit `
        -Arguments @("fetch", "--progress", $script:WorkerRemote, $script:WorkerBranch) `
        -LocalStart 45 `
        -LocalEnd 68 `
        -BasePercent $BasePercent `
        -SpanPercent $SpanPercent `
        -Status "Downloading the latest project data..." `
        -Phase "Download"

    Set-OperationProgress 76 $BasePercent $SpanPercent `
        "Applying downloaded changes..." "Fast-forward"

    Invoke-GitCapture `
        -Arguments @("merge", "--ff-only", "$($script:WorkerRemote)/$($script:WorkerBranch)") |
        Out-Null

    Set-OperationProgress 90 $BasePercent $SpanPercent `
        "Restoring local work..." "Restore"

    if ($stashCreated) {
        # Apply first and drop only after a completely successful restore.
        # This guarantees that the temporary backup remains available when
        # a same-name file arrives from GitHub or another conflict occurs.
        $stashApply = Invoke-GitCapture `
            -Arguments @("stash", "apply", "stash@{0}") `
            -AllowFailure

        if ($stashApply.ExitCode -ne 0) {
            $restoreDetails = @(
                $stashApply.Output |
                    Where-Object { -not [string]::IsNullOrWhiteSpace([string]$_) } |
                    ForEach-Object { [string]$_ }
            ) -join [Environment]::NewLine

            if ([string]::IsNullOrWhiteSpace($restoreDetails)) {
                $restoreDetails = "Git could not restore the temporary stash."
            }

            throw (
                "The project was updated, but local files could not be restored. " +
                "The temporary stash was kept safely as stash@{0}.`r`n`r`n" +
                $restoreDetails
            )
        }

        Invoke-GitCapture -Arguments @("stash", "drop", "stash@{0}") | Out-Null
    }

    Set-OperationProgress 100 $BasePercent $SpanPercent `
        "Project update completed." "Complete"

    Write-WorkerLog "Update operation completed successfully."
}

function Invoke-PushWorker {
    param(
        [int]$BasePercent = 0,
        [int]$SpanPercent = 100
    )

    Write-WorkerLog "Starting save and push operation."

    Set-CommitIdentity `
        -Name ([string]$script:WorkerRequest.name) `
        -Email ([string]$script:WorkerRequest.email)

    Set-OperationProgress 5 $BasePercent $SpanPercent `
        "Opening the shared main branch..." "Branch"

    Invoke-GitCapture -Arguments @("switch", "--quiet", $script:WorkerBranch) | Out-Null

    Set-OperationProgress 15 $BasePercent $SpanPercent `
        "Reviewing local changes..." "Review"

    $statusOutput = @(& git -C $script:WorkerRepo status --porcelain)
    if ($LASTEXITCODE -ne 0) {
        throw "Could not read local changes."
    }

    Write-WorkerLog "$($statusOutput.Count) changed item(s) detected."

    Set-OperationProgress 25 $BasePercent $SpanPercent `
        "Staging all project changes..." "Stage"

    Invoke-GitCapture -Arguments @("add", "-A") | Out-Null

    & git -C $script:WorkerRepo diff --cached --quiet
    $cachedDiffCode = $LASTEXITCODE

    if ($cachedDiffCode -eq 1) {
        Set-OperationProgress 40 $BasePercent $SpanPercent `
            "Creating a Git commit..." "Commit"

        $commitMessage = [string]$script:WorkerRequest.commitMessage

        if ([string]::IsNullOrWhiteSpace($commitMessage)) {
            $commitMessage = "team-sync($($script:WorkerRequest.name)): $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
        }

        Invoke-GitCapture -Arguments @("commit", "-m", $commitMessage) | Out-Null
        Write-WorkerLog "Commit created: $commitMessage"
    }
    elseif ($cachedDiffCode -eq 0) {
        Write-WorkerLog "No new local change required a commit."
    }
    else {
        throw "Could not inspect staged changes."
    }

    Invoke-AnimatedOperationGit `
        -Arguments @("fetch", "--progress", $script:WorkerRemote, $script:WorkerBranch) `
        -LocalStart 48 `
        -LocalEnd 63 `
        -BasePercent $BasePercent `
        -SpanPercent $SpanPercent `
        -Status "Checking GitHub for newer changes..." `
        -Phase "Download"

    Set-OperationProgress 70 $BasePercent $SpanPercent `
        "Rebasing local commits safely..." "Rebase"

    $rebaseResult = Invoke-GitCapture `
        -Arguments @("rebase", "$($script:WorkerRemote)/$($script:WorkerBranch)") `
        -AllowFailure

    if ($rebaseResult.ExitCode -ne 0) {
        throw "Rebase failed or produced conflicts. Open the repository status before retrying."
    }

    Invoke-AnimatedOperationGit `
        -Arguments @("push", "--progress", $script:WorkerRemote, $script:WorkerBranch) `
        -LocalStart 77 `
        -LocalEnd 91 `
        -BasePercent $BasePercent `
        -SpanPercent $SpanPercent `
        -Status "Uploading project changes to GitHub..." `
        -Phase "Upload"

    Set-OperationProgress 95 $BasePercent $SpanPercent `
        "Verifying local and remote commits..." "Verification"

    Invoke-GitCapture `
        -Arguments @("fetch", $script:WorkerRemote, $script:WorkerBranch) |
        Out-Null

    $localHead = (& git -C $script:WorkerRepo rev-parse HEAD).Trim()
    $remoteHead = (& git -C $script:WorkerRepo rev-parse "$($script:WorkerRemote)/$($script:WorkerBranch)").Trim()

    if ($LASTEXITCODE -ne 0) {
        throw "Could not verify the final Git commit."
    }

    if ($localHead -ne $remoteHead) {
        throw "Upload verification failed because local and remote commit hashes differ."
    }

    Set-OperationProgress 100 $BasePercent $SpanPercent `
        "Changes saved and uploaded successfully." "Complete"

    Write-WorkerLog "Push verification completed at commit $localHead."
}

function Invoke-WorkerMain {
    if ([string]::IsNullOrWhiteSpace($RequestPath)) {
        throw "Worker request path was not supplied."
    }

    $script:WorkerRequest = Get-Content -LiteralPath $RequestPath -Raw |
        ConvertFrom-Json

    $script:WorkerRepo = [string]$script:WorkerRequest.repo
    $script:WorkerRemote = [string]$script:WorkerRequest.remote
    $script:WorkerBranch = [string]$script:WorkerRequest.branch
    $script:WorkerLogPath = [string]$script:WorkerRequest.logPath
    $script:WorkerProgressPath = [string]$script:WorkerRequest.progressPath
    $script:WorkerDonePath = [string]$script:WorkerRequest.donePath
    $script:WorkerRuntimePath = Split-Path -Parent $RequestPath
    $script:WorkerLockPath = $null

    [System.IO.File]::WriteAllText(
        $script:WorkerLogPath,
        "$AppName - Git Manager GUI V2`r`n" +
        "Operation: $($script:WorkerRequest.operation)`r`n" +
        "Windows user: $env:USERDOMAIN\$env:USERNAME`r`n" +
        "Computer: $env:COMPUTERNAME`r`n" +
        "Started: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')`r`n" +
        "Repository: $($script:WorkerRepo)`r`n`r`n",
        [System.Text.Encoding]::UTF8
    )

    try {
        Set-WorkerProgress -Percent 1 -Status "Preparing Git operation..." -Phase "Starting"

        Test-WorkerEnvironment
        Acquire-WorkerLock
        Test-UnresolvedConflicts

        switch ([string]$script:WorkerRequest.operation) {
            "Update" {
                Invoke-UpdateWorker
                Complete-Worker -Success $true -Message "Project updated successfully."
            }

            "Push" {
                Invoke-PushWorker
                Complete-Worker -Success $true -Message "Changes saved and uploaded successfully."
            }

            "FullSync" {
                Invoke-UpdateWorker -BasePercent 0 -SpanPercent 45
                Invoke-PushWorker -BasePercent 45 -SpanPercent 55

                Set-WorkerProgress -Percent 100 `
                    -Status "Full synchronization completed." `
                    -Phase "Complete"

                Complete-Worker -Success $true -Message "Full synchronization completed successfully."
            }

            default {
                throw "Unknown worker operation: $($script:WorkerRequest.operation)"
            }
        }
    }
    catch {
        $message = [string]$_.Exception.Message

        if ([string]::IsNullOrWhiteSpace($message)) {
            $message = "An unknown Git operation error occurred."
        }

        Write-WorkerLog "ERROR: $message"
        Set-WorkerProgress -Percent 100 -Status $message -Phase "Failed"
        Complete-Worker -Success $false -Message $message -ExitCode 1
    }
    finally {
        Release-WorkerLock
    }
}


# ============================================================
# Portable repository discovery
# ============================================================

function Resolve-GitRepositoryCandidate {
    param([string]$CandidatePath)

    if ([string]::IsNullOrWhiteSpace($CandidatePath)) {
        return $null
    }

    try {
        $expandedPath = [Environment]::ExpandEnvironmentVariables(
            $CandidatePath.Trim().Trim('"')
        )

        if (-not (Test-Path -LiteralPath $expandedPath)) {
            return $null
        }

        $resolvedPath = (Resolve-Path -LiteralPath $expandedPath).Path
        $repositoryRoot = @(
            & git -C $resolvedPath rev-parse --show-toplevel 2>$null
        )

        if (($LASTEXITCODE -ne 0) -or ($repositoryRoot.Count -eq 0)) {
            return $null
        }

        $root = ([string]$repositoryRoot[-1]).Trim()

        if (
            [string]::IsNullOrWhiteSpace($root) -or
            (-not (Test-Path -LiteralPath $root))
        ) {
            return $null
        }

        return (Resolve-Path -LiteralPath $root).Path
    }
    catch {
        return $null
    }
}

function Get-GuiSettings {
    if (-not (Test-Path -LiteralPath $SettingsPath)) {
        return $null
    }

    try {
        $content = Get-Content -LiteralPath $SettingsPath -Raw

        if ([string]::IsNullOrWhiteSpace($content)) {
            return $null
        }

        return ($content | ConvertFrom-Json)
    }
    catch {
        return $null
    }
}

function Save-GuiSettings {
    param([Parameter(Mandatory = $true)] [string]$RepositoryPath)

    [ordered]@{
        repositoryPath = $RepositoryPath
        remote         = $DefaultRemote
        branch         = $DefaultBranch
        updatedAt      = (Get-Date).ToString("o")
    } |
        ConvertTo-Json -Depth 4 |
        Set-Content -LiteralPath $SettingsPath -Encoding UTF8
}

function Select-GuiRepositoryFolder {
    param([string]$InitialPath = "")

    Add-Type -AssemblyName System.Windows.Forms

    $dialog = New-Object System.Windows.Forms.FolderBrowserDialog
    $dialog.Description =
        "Select the aerial-human-detection project folder or any folder inside that Git repository."
    $dialog.ShowNewFolderButton = $false

    if (
        -not [string]::IsNullOrWhiteSpace($InitialPath) -and
        (Test-Path -LiteralPath $InitialPath)
    ) {
        $dialog.SelectedPath = $InitialPath
    }

    $result = $dialog.ShowDialog()

    if ($result -ne [System.Windows.Forms.DialogResult]::OK) {
        return $null
    }

    return (Resolve-GitRepositoryCandidate -CandidatePath $dialog.SelectedPath)
}

function Resolve-GuiRepositoryPath {
    $settings = Get-GuiSettings
    $savedPath = ""

    if ($settings -and $settings.repositoryPath) {
        $savedPath = [string]$settings.repositoryPath
    }

    $candidatePaths = New-Object System.Collections.Generic.List[string]

    foreach ($candidate in @(
        $savedPath,
        $env:AERIAL_HUMAN_DETECTION_REPO,
        $PSScriptRoot,
        (Get-Location).Path,
        (Join-Path $PSScriptRoot "aerial-human-detection"),
        (Join-Path $env:USERPROFILE "aerial-human-detection"),
        (Join-Path $env:USERPROFILE "Projects\aerial-human-detection"),
        (Join-Path $env:USERPROFILE "Documents\aerial-human-detection"),
        (Join-Path $env:USERPROFILE "Documents\GitHub\aerial-human-detection"),
        (Join-Path $env:USERPROFILE "source\repos\aerial-human-detection"),
        (Join-Path $env:USERPROFILE "Desktop\aerial-human-detection")
    )) {
        if (-not [string]::IsNullOrWhiteSpace([string]$candidate)) {
            $candidatePaths.Add([string]$candidate)
        }
    }

    foreach ($candidate in $candidatePaths) {
        $resolved = Resolve-GitRepositoryCandidate -CandidatePath $candidate

        if ($resolved) {
            Save-GuiSettings -RepositoryPath $resolved
            return $resolved
        }
    }

    [System.Windows.MessageBox]::Show(
        "The project folder is different on this computer.`r`n`r`nSelect the folder that contains the Git project. You may also select any subfolder inside it. The selected path will be saved only on this computer.",
        "Select project folder",
        [System.Windows.MessageBoxButton]::OK,
        [System.Windows.MessageBoxImage]::Information
    ) | Out-Null

    while ($true) {
        $selected = Select-GuiRepositoryFolder -InitialPath $savedPath

        if ($selected) {
            Save-GuiSettings -RepositoryPath $selected
            return $selected
        }

        $answer = [System.Windows.MessageBox]::Show(
            "A valid Git repository was not selected.`r`n`r`nRetry folder selection?",
            "Project folder required",
            [System.Windows.MessageBoxButton]::YesNo,
            [System.Windows.MessageBoxImage]::Warning
        )

        if ($answer -ne [System.Windows.MessageBoxResult]::Yes) {
            return $null
        }
    }
}

# ============================================================
# GUI helpers
# ============================================================

function Test-GuiEmail {
    param([string]$Email)
    return $Email -match '^[^@\s]+@[^@\s]+\.[^@\s]+$'
}

function Get-GuiProfiles {
    if (-not (Test-Path -LiteralPath $ProfilesPath)) {
        return @()
    }

    try {
        $content = Get-Content -LiteralPath $ProfilesPath -Raw

        if ([string]::IsNullOrWhiteSpace($content)) {
            return @()
        }

        return @($content | ConvertFrom-Json)
    }
    catch {
        return @()
    }
}

function Save-GuiProfiles {
    param([object[]]$Profiles)

    @($Profiles) |
        ConvertTo-Json -Depth 5 |
        Set-Content -LiteralPath $ProfilesPath -Encoding UTF8
}

function Invoke-GuiGit {
    param(
        [Parameter(Mandatory = $true)] [string]$Repo,
        [Parameter(Mandatory = $true)] [string[]]$Arguments,
        [switch]$AllowFailure
    )

    # Do not treat Git's informational stderr text as a PowerShell error.
    # The native process exit code is the source of truth.
    $previousErrorActionPreference = $ErrorActionPreference

    try {
        $ErrorActionPreference = "Continue"
        $result = @(& git -C $Repo @Arguments 2>&1)
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }

    $textResult = @($result | ForEach-Object { [string]$_ })

    if (($exitCode -ne 0) -and (-not $AllowFailure)) {
        $details = $textResult -join [Environment]::NewLine

        if ([string]::IsNullOrWhiteSpace($details)) {
            $details = "Git returned exit code $exitCode."
        }

        throw $details
    }

    return [pscustomobject]@{
        ExitCode = $exitCode
        Output   = $textResult
    }
}

function Show-GuiMessage {
    param(
        [Parameter(Mandatory = $true)] [string]$Message,
        [string]$Title = "Git Manager V2",
        [ValidateSet("Info", "Warning", "Error")]
        [string]$Type = "Info"
    )

    $icon = switch ($Type) {
        "Warning" { [System.Windows.MessageBoxImage]::Warning }
        "Error"   { [System.Windows.MessageBoxImage]::Error }
        default   { [System.Windows.MessageBoxImage]::Information }
    }

    [System.Windows.MessageBox]::Show(
        $Message,
        $Title,
        [System.Windows.MessageBoxButton]::OK,
        $icon
    ) | Out-Null
}

function Start-Gui {
    Add-Type -AssemblyName PresentationFramework
    Add-Type -AssemblyName PresentationCore
    Add-Type -AssemblyName WindowsBase
    Add-Type -AssemblyName System.Windows.Forms

    [xml]$xaml = @'
<Window
    xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
    xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
    Title="Aerial Human Detection - Git Manager V2"
    Width="1280"
    Height="820"
    MinWidth="1080"
    MinHeight="700"
    WindowStartupLocation="CenterScreen"
    Background="#0B1220"
    Foreground="#E5E7EB"
    FontFamily="Segoe UI"
    FontSize="13">

    <Window.Resources>
        <SolidColorBrush x:Key="PanelBrush" Color="#111B2E"/>
        <SolidColorBrush x:Key="PanelBorderBrush" Color="#24324A"/>
        <SolidColorBrush x:Key="MutedBrush" Color="#94A3B8"/>
        <SolidColorBrush x:Key="AccentBrush" Color="#38BDF8"/>
        <SolidColorBrush x:Key="SuccessBrush" Color="#22C55E"/>
        <SolidColorBrush x:Key="WarningBrush" Color="#F59E0B"/>
        <SolidColorBrush x:Key="DangerBrush" Color="#EF4444"/>

        <Style x:Key="CardStyle" TargetType="Border">
            <Setter Property="Background" Value="{StaticResource PanelBrush}"/>
            <Setter Property="BorderBrush" Value="{StaticResource PanelBorderBrush}"/>
            <Setter Property="BorderThickness" Value="1"/>
            <Setter Property="CornerRadius" Value="14"/>
            <Setter Property="Padding" Value="16"/>
        </Style>

        <Style x:Key="TitleTextStyle" TargetType="TextBlock">
            <Setter Property="FontSize" Value="17"/>
            <Setter Property="FontWeight" Value="SemiBold"/>
            <Setter Property="Foreground" Value="#F8FAFC"/>
        </Style>

        <Style x:Key="MutedTextStyle" TargetType="TextBlock">
            <Setter Property="Foreground" Value="{StaticResource MutedBrush}"/>
            <Setter Property="FontSize" Value="12"/>
        </Style>

        <Style x:Key="InputStyle" TargetType="TextBox">
            <Setter Property="Background" Value="#0D1728"/>
            <Setter Property="Foreground" Value="#F8FAFC"/>
            <Setter Property="BorderBrush" Value="#334155"/>
            <Setter Property="BorderThickness" Value="1"/>
            <Setter Property="Padding" Value="10,7"/>
            <Setter Property="CaretBrush" Value="#F8FAFC"/>
        </Style>

        <Style x:Key="ComboStyle" TargetType="ComboBox">
            <Setter Property="Background" Value="#0D1728"/>
            <Setter Property="Foreground" Value="#F8FAFC"/>
            <Setter Property="BorderBrush" Value="#334155"/>
            <Setter Property="BorderThickness" Value="1"/>
            <Setter Property="Padding" Value="8,5"/>
        </Style>

        <Style x:Key="BaseButtonStyle" TargetType="Button">
            <Setter Property="Foreground" Value="White"/>
            <Setter Property="Background" Value="#1E293B"/>
            <Setter Property="BorderBrush" Value="#334155"/>
            <Setter Property="BorderThickness" Value="1"/>
            <Setter Property="Padding" Value="14,9"/>
            <Setter Property="Cursor" Value="Hand"/>
            <Setter Property="FontWeight" Value="SemiBold"/>
            <Setter Property="HorizontalContentAlignment" Value="Center"/>
        </Style>

        <Style x:Key="PrimaryButtonStyle" TargetType="Button" BasedOn="{StaticResource BaseButtonStyle}">
            <Setter Property="Background" Value="#0369A1"/>
            <Setter Property="BorderBrush" Value="#0EA5E9"/>
        </Style>

        <Style x:Key="SuccessButtonStyle" TargetType="Button" BasedOn="{StaticResource BaseButtonStyle}">
            <Setter Property="Background" Value="#166534"/>
            <Setter Property="BorderBrush" Value="#22C55E"/>
        </Style>

        <Style x:Key="PurpleButtonStyle" TargetType="Button" BasedOn="{StaticResource BaseButtonStyle}">
            <Setter Property="Background" Value="#6D28D9"/>
            <Setter Property="BorderBrush" Value="#8B5CF6"/>
        </Style>

        <Style x:Key="DangerButtonStyle" TargetType="Button" BasedOn="{StaticResource BaseButtonStyle}">
            <Setter Property="Background" Value="#7F1D1D"/>
            <Setter Property="BorderBrush" Value="#EF4444"/>
        </Style>
    </Window.Resources>

    <Grid>
        <Grid.RowDefinitions>
            <RowDefinition Height="78"/>
            <RowDefinition Height="*"/>
            <RowDefinition Height="34"/>
        </Grid.RowDefinitions>

        <Border Grid.Row="0" Background="#0F1A2D" BorderBrush="#24324A" BorderThickness="0,0,0,1">
            <Grid Margin="24,0">
                <Grid.ColumnDefinitions>
                    <ColumnDefinition Width="*"/>
                    <ColumnDefinition Width="Auto"/>
                </Grid.ColumnDefinitions>

                <StackPanel VerticalAlignment="Center">
                    <TextBlock Text="AERIAL HUMAN DETECTION" FontSize="12" Foreground="#38BDF8" FontWeight="Bold"/>
                    <TextBlock Text="Team Git Manager" FontSize="25" FontWeight="SemiBold" Foreground="#F8FAFC"/>
                </StackPanel>

                <StackPanel Grid.Column="1" Orientation="Horizontal" VerticalAlignment="Center">
                    <Border Background="#10253B" BorderBrush="#1D4ED8" BorderThickness="1" CornerRadius="16" Padding="12,6" Margin="0,0,12,0">
                        <TextBlock x:Name="txtHeaderStatus" Text="Ready" Foreground="#93C5FD" FontWeight="SemiBold"/>
                    </Border>
                    <Border Background="#13251B" BorderBrush="#16A34A" BorderThickness="1" CornerRadius="16" Padding="12,6">
                        <TextBlock Text="GUI V2.4" Foreground="#86EFAC" FontWeight="Bold"/>
                    </Border>
                </StackPanel>
            </Grid>
        </Border>

        <Grid Grid.Row="1" Margin="20">
            <Grid.ColumnDefinitions>
                <ColumnDefinition Width="350"/>
                <ColumnDefinition Width="14"/>
                <ColumnDefinition Width="*"/>
            </Grid.ColumnDefinitions>

            <ScrollViewer Grid.Column="0" VerticalScrollBarVisibility="Auto">
                <StackPanel>
                    <Border Style="{StaticResource CardStyle}" Margin="0,0,0,12">
                        <StackPanel>
                            <TextBlock Text="Project overview" Style="{StaticResource TitleTextStyle}"/>
                            <TextBlock Text="Shared repository health and synchronization state." Style="{StaticResource MutedTextStyle}" Margin="0,4,0,14"/>

                            <Grid>
                                <Grid.ColumnDefinitions>
                                    <ColumnDefinition Width="92"/>
                                    <ColumnDefinition Width="*"/>
                                </Grid.ColumnDefinitions>
                                <Grid.RowDefinitions>
                                    <RowDefinition Height="Auto"/>
                                    <RowDefinition Height="Auto"/>
                                    <RowDefinition Height="Auto"/>
                                    <RowDefinition Height="Auto"/>
                                    <RowDefinition Height="Auto"/>
                                    <RowDefinition Height="Auto"/>
                                </Grid.RowDefinitions>

                                <TextBlock Grid.Row="0" Text="Repository" Foreground="#94A3B8" Margin="0,4"/>
                                <TextBlock Grid.Row="0" Grid.Column="1" x:Name="txtRepo" TextWrapping="Wrap" Foreground="#E2E8F0" Margin="0,4"/>

                                <TextBlock Grid.Row="1" Text="Branch" Foreground="#94A3B8" Margin="0,4"/>
                                <TextBlock Grid.Row="1" Grid.Column="1" x:Name="txtBranch" Foreground="#7DD3FC" FontWeight="SemiBold" Margin="0,4"/>

                                <TextBlock Grid.Row="2" Text="Changes" Foreground="#94A3B8" Margin="0,4"/>
                                <TextBlock Grid.Row="2" Grid.Column="1" x:Name="txtChanges" Foreground="#F8FAFC" Margin="0,4"/>

                                <TextBlock Grid.Row="3" Text="Ahead / Behind" Foreground="#94A3B8" Margin="0,4"/>
                                <TextBlock Grid.Row="3" Grid.Column="1" x:Name="txtAheadBehind" Foreground="#F8FAFC" Margin="0,4"/>

                                <TextBlock Grid.Row="4" Text="Last commit" Foreground="#94A3B8" Margin="0,4"/>
                                <TextBlock Grid.Row="4" Grid.Column="1" x:Name="txtLastCommit" TextWrapping="Wrap" Foreground="#F8FAFC" Margin="0,4"/>

                                <TextBlock Grid.Row="5" Text="Remote" Foreground="#94A3B8" Margin="0,4"/>
                                <TextBlock Grid.Row="5" Grid.Column="1" x:Name="txtRemote" TextWrapping="Wrap" Foreground="#CBD5E1" Margin="0,4"/>
                            </Grid>

                            <Grid Margin="0,14,0,0">
                                <Grid.ColumnDefinitions>
                                    <ColumnDefinition Width="*"/>
                                    <ColumnDefinition Width="8"/>
                                    <ColumnDefinition Width="*"/>
                                </Grid.ColumnDefinitions>
                                <Button Grid.Column="0" x:Name="btnRefresh" Content="Refresh dashboard" Style="{StaticResource BaseButtonStyle}"/>
                                <Button Grid.Column="2" x:Name="btnChangeRepo" Content="Change repository" Style="{StaticResource PrimaryButtonStyle}"/>
                            </Grid>
                        </StackPanel>
                    </Border>

                    <Border Style="{StaticResource CardStyle}" Margin="0,0,0,12">
                        <StackPanel>
                            <TextBlock Text="Commit identity" Style="{StaticResource TitleTextStyle}"/>
                            <TextBlock Text="Choose the teammate credited for the next commit." Style="{StaticResource MutedTextStyle}" Margin="0,4,0,12"/>

                            <TextBlock Text="Saved profiles" Foreground="#CBD5E1" Margin="0,0,0,5"/>
                            <ComboBox x:Name="cmbProfiles" Style="{StaticResource ComboStyle}" DisplayMemberPath="Display"/>

                            <TextBlock Text="Full name" Foreground="#CBD5E1" Margin="0,10,0,5"/>
                            <TextBox x:Name="txtName" Style="{StaticResource InputStyle}"/>

                            <TextBlock Text="GitHub email" Foreground="#CBD5E1" Margin="0,10,0,5"/>
                            <TextBox x:Name="txtEmail" Style="{StaticResource InputStyle}"/>

                            <Grid Margin="0,12,0,0">
                                <Grid.ColumnDefinitions>
                                    <ColumnDefinition Width="*"/>
                                    <ColumnDefinition Width="8"/>
                                    <ColumnDefinition Width="*"/>
                                </Grid.ColumnDefinitions>
                                <Button Grid.Column="0" x:Name="btnApplyIdentity" Content="Apply identity" Style="{StaticResource PrimaryButtonStyle}"/>
                                <Button Grid.Column="2" x:Name="btnSaveProfile" Content="Save profile" Style="{StaticResource SuccessButtonStyle}"/>
                            </Grid>

                            <Button x:Name="btnDeleteProfile" Content="Delete selected profile" Style="{StaticResource DangerButtonStyle}" Margin="0,8,0,0"/>
                        </StackPanel>
                    </Border>

                    <Border Style="{StaticResource CardStyle}">
                        <StackPanel>
                            <TextBlock Text="Commit message" Style="{StaticResource TitleTextStyle}"/>
                            <TextBlock Text="Leave blank to generate a timestamped team message." Style="{StaticResource MutedTextStyle}" Margin="0,4,0,10"/>
                            <TextBox x:Name="txtCommitMessage" Style="{StaticResource InputStyle}" Height="70" TextWrapping="Wrap" AcceptsReturn="True"/>
                        </StackPanel>
                    </Border>
                </StackPanel>
            </ScrollViewer>

            <Grid Grid.Column="2">
                <Grid.RowDefinitions>
                    <RowDefinition Height="Auto"/>
                    <RowDefinition Height="12"/>
                    <RowDefinition Height="Auto"/>
                    <RowDefinition Height="12"/>
                    <RowDefinition Height="*"/>
                </Grid.RowDefinitions>

                <Border Grid.Row="0" Style="{StaticResource CardStyle}">
                    <Grid>
                        <Grid.ColumnDefinitions>
                            <ColumnDefinition Width="*"/>
                            <ColumnDefinition Width="12"/>
                            <ColumnDefinition Width="*"/>
                            <ColumnDefinition Width="12"/>
                            <ColumnDefinition Width="*"/>
                        </Grid.ColumnDefinitions>

                        <Button Grid.Column="0" x:Name="btnUpdate" Height="78" Style="{StaticResource PrimaryButtonStyle}">
                            <StackPanel>
                                <TextBlock Text="UPDATE PROJECT" FontSize="15" FontWeight="Bold" HorizontalAlignment="Center"/>
                                <TextBlock Text="Download latest changes" FontSize="11" Opacity="0.85" HorizontalAlignment="Center" Margin="0,4,0,0"/>
                            </StackPanel>
                        </Button>

                        <Button Grid.Column="2" x:Name="btnPush" Height="78" Style="{StaticResource SuccessButtonStyle}">
                            <StackPanel>
                                <TextBlock Text="SAVE &amp; PUSH" FontSize="15" FontWeight="Bold" HorizontalAlignment="Center"/>
                                <TextBlock Text="Commit and upload work" FontSize="11" Opacity="0.85" HorizontalAlignment="Center" Margin="0,4,0,0"/>
                            </StackPanel>
                        </Button>

                        <Button Grid.Column="4" x:Name="btnFullSync" Height="78" Style="{StaticResource PurpleButtonStyle}">
                            <StackPanel>
                                <TextBlock Text="FULL SYNC" FontSize="15" FontWeight="Bold" HorizontalAlignment="Center"/>
                                <TextBlock Text="Update, commit, and upload" FontSize="11" Opacity="0.85" HorizontalAlignment="Center" Margin="0,4,0,0"/>
                            </StackPanel>
                        </Button>
                    </Grid>
                </Border>

                <Border Grid.Row="2" Style="{StaticResource CardStyle}">
                    <Grid>
                        <Grid.RowDefinitions>
                            <RowDefinition Height="Auto"/>
                            <RowDefinition Height="10"/>
                            <RowDefinition Height="Auto"/>
                            <RowDefinition Height="8"/>
                            <RowDefinition Height="Auto"/>
                        </Grid.RowDefinitions>

                        <Grid>
                            <Grid.ColumnDefinitions>
                                <ColumnDefinition Width="*"/>
                                <ColumnDefinition Width="Auto"/>
                            </Grid.ColumnDefinitions>

                            <StackPanel>
                                <TextBlock Text="Operation progress" Style="{StaticResource TitleTextStyle}"/>
                                <TextBlock x:Name="txtProgressStatus" Text="Ready for the next operation." Style="{StaticResource MutedTextStyle}" Margin="0,4,0,0"/>
                            </StackPanel>

                            <TextBlock Grid.Column="1" x:Name="txtProgressPercent" Text="0%" FontSize="27" FontWeight="Bold" Foreground="#38BDF8" VerticalAlignment="Center"/>
                        </Grid>

                        <ProgressBar Grid.Row="2" x:Name="progressBar" Height="15" Minimum="0" Maximum="100" Value="0" Foreground="#0EA5E9" Background="#0D1728"/>

                        <Grid Grid.Row="4">
                            <Grid.ColumnDefinitions>
                                <ColumnDefinition Width="*"/>
                                <ColumnDefinition Width="Auto"/>
                            </Grid.ColumnDefinitions>

                            <TextBlock x:Name="txtProgressPhase" Text="Idle" Foreground="#CBD5E1"/>
                            <TextBlock Grid.Column="1" x:Name="txtOperationClock" Text="" Foreground="#94A3B8"/>
                        </Grid>
                    </Grid>
                </Border>

                <Border Grid.Row="4" Style="{StaticResource CardStyle}">
                    <Grid>
                        <Grid.RowDefinitions>
                            <RowDefinition Height="Auto"/>
                            <RowDefinition Height="10"/>
                            <RowDefinition Height="*"/>
                            <RowDefinition Height="10"/>
                            <RowDefinition Height="Auto"/>
                        </Grid.RowDefinitions>

                        <Grid>
                            <Grid.ColumnDefinitions>
                                <ColumnDefinition Width="*"/>
                                <ColumnDefinition Width="Auto"/>
                            </Grid.ColumnDefinitions>

                            <StackPanel>
                                <TextBlock Text="Live activity" Style="{StaticResource TitleTextStyle}"/>
                                <TextBlock Text="Git output, transfer messages, verification, and errors." Style="{StaticResource MutedTextStyle}" Margin="0,4,0,0"/>
                            </StackPanel>

                            <StackPanel Grid.Column="1" Orientation="Horizontal">
                                <Button x:Name="btnRecentCommits" Content="Recent commits" Style="{StaticResource BaseButtonStyle}" Margin="0,0,8,0"/>
                                <Button x:Name="btnOpenLogs" Content="Open logs" Style="{StaticResource BaseButtonStyle}" Margin="0,0,8,0"/>
                                <Button x:Name="btnClearLog" Content="Clear" Style="{StaticResource BaseButtonStyle}"/>
                            </StackPanel>
                        </Grid>

                        <TextBox Grid.Row="2"
                                 x:Name="txtLog"
                                 Background="#08101D"
                                 Foreground="#D1FAE5"
                                 BorderBrush="#24324A"
                                 BorderThickness="1"
                                 FontFamily="Consolas"
                                 FontSize="12"
                                 Padding="12"
                                 IsReadOnly="True"
                                 AcceptsReturn="True"
                                 TextWrapping="NoWrap"
                                 VerticalScrollBarVisibility="Auto"
                                 HorizontalScrollBarVisibility="Auto"/>

                        <Grid Grid.Row="4">
                            <Grid.ColumnDefinitions>
                                <ColumnDefinition Width="*"/>
                                <ColumnDefinition Width="Auto"/>
                            </Grid.ColumnDefinitions>

                            <TextBlock Text="Tip: update before editing, then save and push when finished." Foreground="#94A3B8"/>
                            <Button Grid.Column="1" x:Name="btnRemoveLock" Content="Remove stale lock" Style="{StaticResource DangerButtonStyle}"/>
                        </Grid>
                    </Grid>
                </Border>
            </Grid>
        </Grid>

        <Border Grid.Row="2" Background="#0F1A2D" BorderBrush="#24324A" BorderThickness="0,1,0,0">
            <Grid Margin="20,0">
                <Grid.ColumnDefinitions>
                    <ColumnDefinition Width="*"/>
                    <ColumnDefinition Width="Auto"/>
                </Grid.ColumnDefinitions>

                <TextBlock x:Name="txtFooterStatus" Text="Ready" VerticalAlignment="Center" Foreground="#94A3B8"/>
                <TextBlock Grid.Column="1" Text="One shared folder • One central main branch • Protected Git operations" VerticalAlignment="Center" Foreground="#64748B"/>
            </Grid>
        </Border>
    </Grid>
</Window>
'@

    $reader = New-Object System.Xml.XmlNodeReader $xaml
    $window = [Windows.Markup.XamlReader]::Load($reader)

    $iconPath = Join-Path $PSScriptRoot "git-manager-v2.ico"
    if (Test-Path -LiteralPath $iconPath) {
        try {
            $window.Icon = [System.Windows.Media.Imaging.BitmapFrame]::Create(
                [uri]$iconPath
            )
        }
        catch {
            # The GUI still works if Windows cannot load the optional icon.
        }
    }

    $controlNames = @(
        "txtHeaderStatus", "txtRepo", "txtBranch", "txtChanges",
        "txtAheadBehind", "txtLastCommit", "txtRemote", "btnRefresh",
        "btnChangeRepo",
        "cmbProfiles", "txtName", "txtEmail", "btnApplyIdentity",
        "btnSaveProfile", "btnDeleteProfile", "txtCommitMessage",
        "btnUpdate", "btnPush", "btnFullSync", "txtProgressStatus",
        "txtProgressPercent", "progressBar", "txtProgressPhase",
        "txtOperationClock", "txtLog", "btnRecentCommits",
        "btnOpenLogs", "btnClearLog", "btnRemoveLock", "txtFooterStatus"
    )

    $controls = @{}
    foreach ($name in $controlNames) {
        $controls[$name] = $window.FindName($name)
    }

    $script:GuiRepo = Resolve-GuiRepositoryPath

    if ([string]::IsNullOrWhiteSpace($script:GuiRepo)) {
        $window.Close()
        return
    }

    $script:GuiRemote = $DefaultRemote
    $script:GuiBranch = $DefaultBranch
    $script:GuiProfiles = @()
    $script:WorkerProcess = $null
    $script:OperationStartedAt = $null
    $script:CurrentLogPath = $null
    $script:CurrentProgressPath = $null
    $script:CurrentDonePath = $null
    $script:CurrentRequestPath = $null

    $controls.txtRepo.Text = $script:GuiRepo

    function Set-GuiBusy {
        param([bool]$Busy)

        foreach ($buttonName in @(
            "btnUpdate", "btnPush", "btnFullSync", "btnRefresh", "btnChangeRepo",
            "btnApplyIdentity", "btnSaveProfile", "btnDeleteProfile",
            "btnRemoveLock"
        )) {
            $controls[$buttonName].IsEnabled = -not $Busy
        }

        $controls.txtHeaderStatus.Text = if ($Busy) { "Working" } else { "Ready" }
        $controls.txtFooterStatus.Text = if ($Busy) {
            "A protected Git operation is running."
        }
        else {
            "Ready"
        }
    }

    function Refresh-GuiProfiles {
        $script:GuiProfiles = @(Get-GuiProfiles)

        $displayProfiles = foreach ($profile in $script:GuiProfiles) {
            [pscustomobject]@{
                Name    = [string]$profile.name
                Email   = [string]$profile.email
                Display = "$($profile.name)  <$($profile.email)>"
            }
        }

        $controls.cmbProfiles.ItemsSource = $displayProfiles
    }

    function Load-CurrentIdentity {
        $nameResult = Invoke-GuiGit `
            -Repo $script:GuiRepo `
            -Arguments @("config", "--local", "--get", "user.name") `
            -AllowFailure

        $emailResult = Invoke-GuiGit `
            -Repo $script:GuiRepo `
            -Arguments @("config", "--local", "--get", "user.email") `
            -AllowFailure

        if ($nameResult.ExitCode -eq 0) {
            $controls.txtName.Text = ($nameResult.Output -join "").Trim()
        }

        if ($emailResult.ExitCode -eq 0) {
            $controls.txtEmail.Text = ($emailResult.Output -join "").Trim()
        }
    }

    function Apply-Identity {
        $name = $controls.txtName.Text.Trim()
        $email = $controls.txtEmail.Text.Trim()

        if ([string]::IsNullOrWhiteSpace($name)) {
            Show-GuiMessage -Message "Enter the teammate's full name." -Type Warning
            return $false
        }

        if (-not (Test-GuiEmail $email)) {
            Show-GuiMessage -Message "Enter a valid GitHub email address." -Type Warning
            return $false
        }

        Invoke-GuiGit `
            -Repo $script:GuiRepo `
            -Arguments @("config", "--local", "user.name", $name) |
            Out-Null

        Invoke-GuiGit `
            -Repo $script:GuiRepo `
            -Arguments @("config", "--local", "user.email", $email) |
            Out-Null

        $controls.txtFooterStatus.Text = "Commit identity applied: $name"
        return $true
    }

    function Save-CurrentProfile {
        if (-not (Apply-Identity)) {
            return
        }

        $name = $controls.txtName.Text.Trim()
        $email = $controls.txtEmail.Text.Trim()

        $existingIndex = -1
        for ($index = 0; $index -lt $script:GuiProfiles.Count; $index++) {
            if (
                ([string]$script:GuiProfiles[$index].name -eq $name) -and
                ([string]$script:GuiProfiles[$index].email -eq $email)
            ) {
                $existingIndex = $index
                break
            }
        }

        if ($existingIndex -lt 0) {
            $script:GuiProfiles += [pscustomobject]@{
                name  = $name
                email = $email
            }

            Save-GuiProfiles -Profiles $script:GuiProfiles
            Refresh-GuiProfiles
            Show-GuiMessage -Message "The teammate profile was saved."
        }
        else {
            Show-GuiMessage -Message "This teammate profile is already saved."
        }
    }

    function Delete-SelectedProfile {
        $selected = $controls.cmbProfiles.SelectedItem

        if ($null -eq $selected) {
            Show-GuiMessage -Message "Select a saved profile first." -Type Warning
            return
        }

        $answer = [System.Windows.MessageBox]::Show(
            "Delete the selected teammate profile?",
            "Delete profile",
            [System.Windows.MessageBoxButton]::YesNo,
            [System.Windows.MessageBoxImage]::Question
        )

        if ($answer -ne [System.Windows.MessageBoxResult]::Yes) {
            return
        }

        $script:GuiProfiles = @(
            $script:GuiProfiles | Where-Object {
                -not (
                    ([string]$_.name -eq [string]$selected.Name) -and
                    ([string]$_.email -eq [string]$selected.Email)
                )
            }
        )

        Save-GuiProfiles -Profiles $script:GuiProfiles
        Refresh-GuiProfiles
        Show-GuiMessage -Message "The profile was deleted."
    }

    function Refresh-Dashboard {
        try {
            if (-not (Test-Path -LiteralPath (Join-Path $script:GuiRepo ".git"))) {
                throw "The configured repository is not available."
            }

            $branch = (
                Invoke-GuiGit `
                    -Repo $script:GuiRepo `
                    -Arguments @("branch", "--show-current")
            ).Output -join ""

            $remote = (
                Invoke-GuiGit `
                    -Repo $script:GuiRepo `
                    -Arguments @("remote", "get-url", $script:GuiRemote)
            ).Output -join ""

            $status = (
                Invoke-GuiGit `
                    -Repo $script:GuiRepo `
                    -Arguments @("status", "--porcelain")
            ).Output

            $aheadBehindResult = Invoke-GuiGit `
                -Repo $script:GuiRepo `
                -Arguments @(
                    "rev-list",
                    "--left-right",
                    "--count",
                    "$($script:GuiRemote)/$($script:GuiBranch)...HEAD"
                ) `
                -AllowFailure

            $behind = "?"
            $ahead = "?"

            if ($aheadBehindResult.ExitCode -eq 0) {
                $parts = (($aheadBehindResult.Output -join " ").Trim() -split "\s+")

                if ($parts.Count -ge 2) {
                    $behind = $parts[0]
                    $ahead = $parts[1]
                }
            }

            $lastCommit = (
                Invoke-GuiGit `
                    -Repo $script:GuiRepo `
                    -Arguments @(
                        "log", "-1",
                        "--pretty=format:%h  %ad  %an  %s",
                        "--date=short"
                    )
            ).Output -join ""

            $controls.txtBranch.Text = $branch.Trim()
            $controls.txtRemote.Text = $remote.Trim()
            $controls.txtChanges.Text = "$($status.Count) changed item(s)"
            $controls.txtAheadBehind.Text = "$ahead ahead / $behind behind"
            $controls.txtLastCommit.Text = $lastCommit.Trim()
            $controls.txtFooterStatus.Text = "Dashboard refreshed at $(Get-Date -Format 'HH:mm:ss')."
        }
        catch {
            $controls.txtFooterStatus.Text = "Dashboard refresh failed."
            $controls.txtLog.Text = "Dashboard error:`r`n$($_.Exception.Message)`r`n`r`nUse Change repository to select the correct project folder on this computer."
        }
    }

    function Show-RecentCommits {
        try {
            $history = Invoke-GuiGit `
                -Repo $script:GuiRepo `
                -Arguments @(
                    "log", "-20",
                    "--graph",
                    "--decorate",
                    "--date=short",
                    "--pretty=format:%h  %ad  %an  %s"
                )

            $controls.txtLog.Text = "RECENT COMMITS`r`n" +
                ("=" * 92) + "`r`n" +
                ($history.Output -join "`r`n")

            $controls.txtLog.ScrollToEnd()
        }
        catch {
            Show-GuiMessage -Message $_.Exception.Message -Type Error
        }
    }

    function Start-GitOperation {
        param(
            [ValidateSet("Update", "Push", "FullSync")]
            [string]$Operation
        )

        if ($script:WorkerProcess -and (-not $script:WorkerProcess.HasExited)) {
            Show-GuiMessage -Message "A Git operation is already running." -Type Warning
            return
        }

        if ($Operation -in @("Push", "FullSync")) {
            if (-not (Apply-Identity)) {
                return
            }
        }

        $sessionId = [guid]::NewGuid().ToString("N")
        $requestPath = Join-Path $RuntimePath "request-$sessionId.json"
        $progressPath = Join-Path $RuntimePath "progress-$sessionId.json"
        $donePath = Join-Path $RuntimePath "done-$sessionId.json"
        $logPath = Join-Path $LogsPath (
            "$($Operation.ToLower())-$(Get-Date -Format 'yyyyMMdd-HHmmss').log"
        )

        $request = [ordered]@{
            operation     = $Operation
            repo          = $script:GuiRepo
            remote        = $script:GuiRemote
            branch        = $script:GuiBranch
            name          = $controls.txtName.Text.Trim()
            email         = $controls.txtEmail.Text.Trim()
            commitMessage = $controls.txtCommitMessage.Text.Trim()
            progressPath  = $progressPath
            donePath      = $donePath
            logPath       = $logPath
        }

        $request |
            ConvertTo-Json -Depth 5 |
            Set-Content -LiteralPath $requestPath -Encoding UTF8

        $script:CurrentRequestPath = $requestPath
        $script:CurrentProgressPath = $progressPath
        $script:CurrentDonePath = $donePath
        $script:CurrentLogPath = $logPath
        $script:OperationStartedAt = Get-Date

        $controls.progressBar.Value = 0
        $controls.txtProgressPercent.Text = "0%"
        $controls.txtProgressStatus.Text = "Starting $Operation operation..."
        $controls.txtProgressPhase.Text = "Starting"
        $controls.txtLog.Text = ""
        $controls.txtOperationClock.Text = "00:00"

        Set-GuiBusy -Busy $true

        $arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`" -Mode Worker -RequestPath `"$requestPath`""

        try {
            $script:WorkerProcess = Start-Process `
                -FilePath "powershell.exe" `
                -ArgumentList $arguments `
                -WindowStyle Hidden `
                -PassThru

            $operationTimer.Start()
        }
        catch {
            Set-GuiBusy -Busy $false
            Show-GuiMessage -Message $_.Exception.Message -Type Error
        }
    }

    $operationTimer = New-Object System.Windows.Threading.DispatcherTimer
    $operationTimer.Interval = [TimeSpan]::FromMilliseconds(300)

    $operationTimer.Add_Tick({
        try {
            if ($script:OperationStartedAt) {
                $elapsed = (Get-Date) - $script:OperationStartedAt
                $controls.txtOperationClock.Text = "{0:mm\:ss}" -f $elapsed
            }

            if (
                $script:CurrentProgressPath -and
                (Test-Path -LiteralPath $script:CurrentProgressPath)
            ) {
                try {
                    $progress = Get-Content `
                        -LiteralPath $script:CurrentProgressPath `
                        -Raw |
                        ConvertFrom-Json

                    $controls.progressBar.Value = [double]$progress.percent
                    $controls.txtProgressPercent.Text = "$($progress.percent)%"
                    $controls.txtProgressStatus.Text = [string]$progress.status
                    $controls.txtProgressPhase.Text = [string]$progress.phase
                    $controls.txtHeaderStatus.Text = [string]$progress.phase
                }
                catch {
                    # Ignore a short-lived read collision while the worker replaces the JSON file.
                }
            }

            if (
                $script:CurrentLogPath -and
                (Test-Path -LiteralPath $script:CurrentLogPath)
            ) {
                $logText = Get-Content -LiteralPath $script:CurrentLogPath -Raw

                if ($controls.txtLog.Text -ne $logText) {
                    $controls.txtLog.Text = $logText
                    $controls.txtLog.ScrollToEnd()
                }
            }

            if (
                $script:CurrentDonePath -and
                (Test-Path -LiteralPath $script:CurrentDonePath)
            ) {
                $done = Get-Content -LiteralPath $script:CurrentDonePath -Raw |
                    ConvertFrom-Json

                $operationTimer.Stop()
                Set-GuiBusy -Busy $false
                Refresh-Dashboard

                if ([bool]$done.success) {
                    $controls.progressBar.Value = 100
                    $controls.txtProgressPercent.Text = "100%"
                    $controls.txtHeaderStatus.Text = "Completed"
                    $controls.txtFooterStatus.Text = [string]$done.message

                    Show-GuiMessage `
                        -Message ([string]$done.message) `
                        -Title "Operation completed"
                }
                else {
                    $controls.txtHeaderStatus.Text = "Failed"
                    $controls.txtFooterStatus.Text = [string]$done.message

                    Show-GuiMessage `
                        -Message ([string]$done.message) `
                        -Title "Git operation failed" `
                        -Type Error
                }

                foreach ($path in @(
                    $script:CurrentDonePath,
                    $script:CurrentProgressPath,
                    $script:CurrentRequestPath
                )) {
                    Remove-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue
                }
            }
            elseif (
                $script:WorkerProcess -and
                $script:WorkerProcess.HasExited -and
                (-not (Test-Path -LiteralPath $script:CurrentDonePath))
            ) {
                $operationTimer.Stop()
                Set-GuiBusy -Busy $false
                $controls.txtHeaderStatus.Text = "Stopped"
                $controls.txtFooterStatus.Text = "The background worker stopped unexpectedly."

                Show-GuiMessage `
                    -Message "The Git worker stopped unexpectedly. Open the logs folder for details." `
                    -Type Error
            }
        }
        catch {
            $operationTimer.Stop()
            Set-GuiBusy -Busy $false

            Show-GuiMessage `
                -Message $_.Exception.Message `
                -Title "GUI monitoring error" `
                -Type Error
        }
    })

    $controls.btnRefresh.Add_Click({
        Refresh-Dashboard
    })

    $controls.btnChangeRepo.Add_Click({
        if ($script:WorkerProcess -and (-not $script:WorkerProcess.HasExited)) {
            Show-GuiMessage `
                -Message "Wait for the current Git operation to finish before changing the repository." `
                -Type Warning
            return
        }

        $selectedRepository = Select-GuiRepositoryFolder `
            -InitialPath $script:GuiRepo

        if (-not $selectedRepository) {
            Show-GuiMessage `
                -Message "The selected folder is not inside a valid Git repository." `
                -Type Warning
            return
        }

        $script:GuiRepo = $selectedRepository
        Save-GuiSettings -RepositoryPath $script:GuiRepo

        $controls.txtRepo.Text = $script:GuiRepo
        $controls.txtName.Clear()
        $controls.txtEmail.Clear()

        Load-CurrentIdentity
        Refresh-Dashboard

        Show-GuiMessage `
            -Message "Repository path saved for this computer:`r`n$($script:GuiRepo)"
    })

    $controls.cmbProfiles.Add_SelectionChanged({
        $selected = $controls.cmbProfiles.SelectedItem

        if ($selected) {
            $controls.txtName.Text = [string]$selected.Name
            $controls.txtEmail.Text = [string]$selected.Email
        }
    })

    $controls.btnApplyIdentity.Add_Click({
        if (Apply-Identity) {
            Show-GuiMessage -Message "The commit identity was applied to this repository."
        }
    })

    $controls.btnSaveProfile.Add_Click({
        Save-CurrentProfile
    })

    $controls.btnDeleteProfile.Add_Click({
        Delete-SelectedProfile
    })

    $controls.btnUpdate.Add_Click({
        Start-GitOperation -Operation Update
    })

    $controls.btnPush.Add_Click({
        Start-GitOperation -Operation Push
    })

    $controls.btnFullSync.Add_Click({
        $answer = [System.Windows.MessageBox]::Show(
            "Full Sync will update the repository, then commit and upload local work. Continue?",
            "Full synchronization",
            [System.Windows.MessageBoxButton]::YesNo,
            [System.Windows.MessageBoxImage]::Question
        )

        if ($answer -eq [System.Windows.MessageBoxResult]::Yes) {
            Start-GitOperation -Operation FullSync
        }
    })

    $controls.btnRecentCommits.Add_Click({
        Show-RecentCommits
    })

    $controls.btnOpenLogs.Add_Click({
        Start-Process explorer.exe -ArgumentList "`"$LogsPath`""
    })

    $controls.btnClearLog.Add_Click({
        $controls.txtLog.Clear()
    })

    $controls.btnRemoveLock.Add_Click({
        $lockPath = Join-Path $script:GuiRepo ".git\team-sync.lock"

        if (-not (Test-Path -LiteralPath $lockPath)) {
            Show-GuiMessage -Message "No Git operation lock exists."
            return
        }

        $ownerPath = Join-Path $lockPath "owner.txt"
        $ownerText = ""

        if (Test-Path -LiteralPath $ownerPath) {
            $ownerText = Get-Content -LiteralPath $ownerPath -Raw
        }

        $answer = [System.Windows.MessageBox]::Show(
            "Remove the Git operation lock?`r`n`r`n$ownerText`r`nOnly do this when no teammate is updating or pushing.",
            "Remove stale lock",
            [System.Windows.MessageBoxButton]::YesNo,
            [System.Windows.MessageBoxImage]::Warning
        )

        if ($answer -eq [System.Windows.MessageBoxResult]::Yes) {
            Remove-Item -LiteralPath $lockPath -Recurse -Force
            Show-GuiMessage -Message "The stale lock was removed."
        }
    })

    $window.Add_Closing({
        param($sender, $eventArgs)

        if ($script:WorkerProcess -and (-not $script:WorkerProcess.HasExited)) {
            [System.Windows.MessageBox]::Show(
                "A Git operation is still running. Keep the application open until it finishes.",
                "Operation in progress",
                [System.Windows.MessageBoxButton]::OK,
                [System.Windows.MessageBoxImage]::Warning
            ) | Out-Null

            $eventArgs.Cancel = $true
        }
    })

    Refresh-GuiProfiles
    Load-CurrentIdentity
    Refresh-Dashboard

    $controls.txtLog.Text =
        "Aerial Human Detection - Git Manager GUI V2`r`n" +
        ("=" * 92) + "`r`n" +
        "1. Update the project before editing files.`r`n" +
        "2. Select the correct teammate identity.`r`n" +
        "3. Save and push when the work is finished.`r`n" +
        "4. Full Sync performs both operations in sequence.`r`n" +
        "5. The repository path is detected automatically and saved per computer.`r`n"

    $window.ShowDialog() | Out-Null
}

# ============================================================
# Entry point
# ============================================================

if ($Mode -eq "Worker") {
    Invoke-WorkerMain
    exit
}

Start-Gui
