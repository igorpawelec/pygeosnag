---
name: sync
description: Which computer this session runs on, repo state (branch, unpushed commits, dirty files) and whether Claude Code chat snapshots need to be exported or imported between the user's computers. Use when the user asks where they are working, is about to switch computers, mentions another computer, or asks whether chats or memory are up to date.
---

<!-- Copy of <personal OneDrive>\ClaudeCode-sync\repo-skills\sync\SKILL.md, kept in the repository so that cloud sessions
     and fresh clones know the rules too. Edit the OneDrive copy and refresh this one with
     ClaudeCode-sync\Publish-MachinesRule.ps1. -->


# Sync status between the user's computers

The computers, paths and routine are in `.claude/rules/machines.md`. On a local Windows computer
the sync folder is `$env:OneDriveConsumer\ClaudeCode-sync`; run

```
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$env:OneDriveConsumer/ClaudeCode-sync/Sync-ClaudeCode.ps1" -Status
```

and tell the user, in Polish, in a few lines: which computer this is; repos with commits not
pushed, uncommitted files, or behind origin; whether this computer's snapshot is stale; which other
computers' snapshots are not yet imported here. Recommend the next command when one is due:
`Sync-ClaudeCode.ps1 -Export` before leaving (normally automatic), or `git pull`, close the Claude
app, `Sync-ClaudeCode.ps1 -Import` on arrival. Never run `-Import` from inside a session.

If the sync folder does not exist, this is a cloud or foreign session: say so, report `git status
-sb` only, and remind that chats and memory of the local computers are not reachable from here.
