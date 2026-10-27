---
name: koniec
description: Session-closing routine. Trigger on /koniec or when the user says "Koniec", "koniec", "kończymy", "zamykamy", "zmieniam komputer", "idę", "na dziś koniec". Writes the session summary to project memory, shows uncommitted work, commits and pushes only after the user confirms, runs the chat export on a local computer, and says whether it is safe to switch computers.
---

<!-- Copy of <personal OneDrive>\ClaudeCode-sync\repo-skills\koniec\SKILL.md, kept in the repository so that cloud sessions
     and fresh clones know the rules too. Edit the OneDrive copy and refresh this one with
     ClaudeCode-sync\Publish-MachinesRule.ps1. -->


# End of a working session

1. **Summary to memory.** On a local computer write (or update) in
   `~/.claude/projects/<project folder>/memory/MEMORY.md` a short dated entry: what was done, what
   is unfinished, decisions taken, next step; under 15 lines; replace an older entry for the same
   day. In a cloud session there is no project memory: put the summary in the final message instead.
   Knowledge that belongs to the project itself (a convention, how to run something) goes into the
   repository's `CLAUDE.md` or `.claude/rules/`, and say so.
2. **Repository.** `git status -sb`. List uncommitted changes one per line and ask: "Commituję i
   wypycham?" Propose the commit message (English, imperative, no attribution, per
   `.claude/rules/authorship.md`). Commit and push only after the user says yes, to the branch the
   session was told to use. If the branch is behind origin, say so; do not pull or merge on your own.
3. **Export** (local computers only, when `$env:OneDriveConsumer\ClaudeCode-sync` exists):
   ```
   powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$env:OneDriveConsumer/ClaudeCode-sync/Auto-Export.ps1" -Force
   ```
   then show the last line of `$env:OneDriveConsumer\ClaudeCode-sync\auto-export.log`. A warning
   that this session is still running is expected; the SessionEnd hook repeats the export on close.
4. **Verdict**, in Polish, three lines at most: what was saved, repo state (pushed / not pushed /
   nothing to commit), and "Można zmieniać komputer" or what still blocks it. In a cloud session the
   verdict is about the push only.
