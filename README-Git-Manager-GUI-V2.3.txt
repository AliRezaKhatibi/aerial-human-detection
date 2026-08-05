Aerial Human Detection - Git Manager GUI V2.3 Portable

FIXED IN V2.3
- Replaced Start-Process for animated Git transfers with System.Diagnostics.Process.
- Prevented false failures after successful git fetch output.
- Reads stdout and stderr asynchronously without deadlocks.
- Waits for process and output streams to finish before checking ExitCode.
- Real Git failures now include the complete Git error text.
- Portable repository selection and all GUI V2 features remain available.

RUN
Double-click:
    Launch-Git-Manager-GUI-V2.3.vbs

Alternative:
    launch-git-manager-gui-v2.3.cmd

Extract all files before launching.
