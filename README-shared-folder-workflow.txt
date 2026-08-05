Aerial Human Detection — shared-folder Git workflow

Files:
1. update-project.cmd
   - Gets the latest origin/main
   - Temporarily stashes uncommitted changes
   - Restores them after the update

2. save-and-push.cmd
   - Stages all changes
   - Creates one commit
   - Rebases on the latest origin/main
   - Pushes directly to origin/main

Repository:
D:\A_Senior - Data Science\Projects\aerial-human-detection

Important rules:
- All users work in the same working tree and the same branch: main.
- Only one person may edit/run Git scripts at a time.
- Do not run both scripts simultaneously.
- A lock folder prevents simultaneous update/push operations.
- Every Windows account must have write permission to the project folder.
- Every Windows account must authenticate to the same GitHub repository.
- Every Windows account must configure Git identity once:
    git config --global user.name "Full Name"
    git config --global user.email "GitHub email"

Recommended placement:
- Keep the two CMD files in the repository root or in one shared tools folder.
- Do not edit the scripts separately for each teammate.
- Do not create personal origin URLs. origin must point to one central repository.

Current origin can be checked with:
    git remote -v

Before first use, resolve any existing merge conflicts:
    git status
    git diff --name-only --diff-filter=U

If a stale lock remains after a forced shutdown and nobody is running a script, delete:
    D:\A_Senior - Data Science\Projects\aerial-human-detection\.git	eam-sync.lock
