---
name: start
description: Session-opening briefing. Trigger on /start or when the user opens with "Start", "start", "meldunek", "briefing", "zaczynamy", "gdzie jesteśmy", "co ostatnio robiliśmy". Checks which computer this is, repo state, unimported chat snapshots, project memory and recent commits, then reports and asks what to do today.
---

<!-- Copy of <personal OneDrive>\ClaudeCode-sync\repo-skills\start\SKILL.md, kept in the repository so that cloud sessions
     and fresh clones know the rules too. Edit the OneDrive copy and refresh this one with
     ClaudeCode-sync\Publish-MachinesRule.ps1. -->


# Start of a working session

Read-only steps, then a report. Do not change files or run git write commands here.

1. **Where we are.** On one of the user's Windows computers the sync folder is
   `$env:OneDriveConsumer\ClaudeCode-sync` (see `.claude/rules/machines.md`). If it exists, run
   ```
   powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$env:OneDriveConsumer/ClaudeCode-sync/Sync-ClaudeCode.ps1" -Status -Brief
   ```
   and take the computer label, repo state and pending imports from its `[claude-sync]` lines.
   If the folder does not exist (cloud session, Linux container, other machine), say in one line
   that this is a cloud or foreign session without access to the local chats, and continue with git.
2. **Repository.** `git status -sb` and `git log --oneline -8`: branch, uncommitted files, commits
   not pushed, behind origin.
3. **What was done last.** Read, if present: the repository's `CLAUDE.md`, `CLAUDE.local.md`, and
   on a local computer the project memory `~/.claude/projects/<project folder>/memory/MEMORY.md`
   (project folder = working directory path with every non-alphanumeric character replaced by `-`).
   Take the last session's notes and open items from there.
4. **Pending sync work** (local computers only): snapshots from other computers not yet imported
   (import needs the Claude app closed, so only tell the user); errors in the last three lines of
   `$env:OneDriveConsumer\ClaudeCode-sync\auto-export.log`, if any.

Report in Polish, at most ten lines: computer (or "sesja w chmurze") and repo in one line; last
work and open items; anything to push, pull or import; then "Co robimy dzisiaj?". If the user
already said what to do in the same message, skip the question and start.
