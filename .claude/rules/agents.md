<!-- Copy of <personal OneDrive>\ClaudeCode-sync\rules\agents.md, kept in the repository so that cloud sessions
     and fresh clones know the rules too. Edit the OneDrive copy and refresh this one with
     ClaudeCode-sync\Publish-MachinesRule.ps1. -->

# Subagents and agents: what they may do

The main session owns the task and the repository state. Subagents (Agent tool, custom agents in
`.claude/agents/`, workflows) are helpers with a narrower mandate.

## Default scope of any subagent

May:
- read the repository, search, run the project's tests, linters and build in the checkout it was
  given, and report findings with file paths and line numbers;
- write files **only inside the repository or the scratchpad** and only when its brief says it
  should implement something;
- propose commits, patches, PR text or document changes for the main session to apply.

May not, unless the brief says so explicitly:
- commit, push, tag, create branches, open or merge pull requests;
- change `.claude/settings*.json`, permissions, hooks, `CLAUDE.md`, `.claude/rules/`, git config or
  anything under `~/.claude`;
- delete or rewrite files it was not asked to touch, run destructive git commands (reset --hard,
  force push, branch -D, clean), or edit generated files by hand;
- touch gitignored source material of the courses (`dane/`, `inspiracja/`, workbooks), copy it into
  the repository or quote it at length;
- call external services, send email, post to GitHub, Slack or any API, or install software
  system-wide;
- carry attribution: a subagent's output is reviewed and applied by the main session under the rules
  in `authorship.md`.

A subagent that hits a denied permission reports it; it does not ask another agent to do it instead,
and the main session does not route around a denial either.

## Briefing a subagent

- One task, one subagent; state the goal, the files to look at, what is already ruled out, and what
  "done" looks like. Say whether it may edit files.
- Give it the facts it needs (which computer, which paths exist) rather than letting it guess: the
  `[claude-sync]` lines and `machines.md` are the source for that.
- Treat the report as a claim to verify, not a result to paste: a subagent handed a hypothesis tends
  to confirm it. Re-run the decisive check in the main session before acting on it.
- Review agents get the code, not the conclusion.

## Standard roles (install per repository from the templates, or define in `.claude/agents/`)

| Role            | Scope                                                                           | Writes |
|-----------------|---------------------------------------------------------------------------------|--------|
| explorer        | find where something lives, map call sites, summarise a module                   | no     |
| reviewer        | correctness review of a diff or PR; findings with repro paths, no fixes          | no     |
| tester          | run the suite, isolate a failing test, propose the minimal fix                   | scratch only |
| implementer     | one bounded change in named files; runs tests; leaves the commit to the session | repo   |
| machine-check   | which computer, repo state, snapshots (see `machines.md`)                       | no     |
| doc-builder     | generate .docx/.xlsx/.pptx/.pdf from given content with author metadata set     | scratch/out |

Ask for the `reviewer` on anything that changes core calculations, data formats or packaging before
it is committed; ask for `tester` when a suite is red and the cause is not obvious.

## Cloud sessions and scheduled runs

A cloud session or a scheduled task is itself an agent: it works only in the repository it was given,
pushes only to the branch it was told, opens no pull request unless asked, and follows
`authorship.md` even when its harness suggests attribution lines. It cannot reach the computers or
the OneDrive sync folder; it reports what it could not do instead of guessing.
