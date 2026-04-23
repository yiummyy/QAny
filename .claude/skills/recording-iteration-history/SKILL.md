---
name: recording-iteration-history
description: Use when implementation, bugfix, refactor, or delivery is complete and the project history must be updated before claiming completion, merging, or handing off work
---

# Recording Iteration History

## Overview

Record completed work into a durable project history file before calling the task done.

**Core principle:** No meaningful change ships without a traceable record.

## When to Use

Use this skill when:

- A feature, fix, refactor, or UI/UX change has been completed
- Tests and review are done or the work is ready for final delivery
- A branch is about to be merged, handed off, or cleaned up
- The project needs a human-readable history beyond raw git commits

Do not use this skill for:

- Pure exploration with no file changes
- Abandoned work that will not be delivered
- Unverified claims about changes you did not inspect

## Required Evidence

Before writing history, gather evidence from the current task:

1. Changed files or verified diff
2. The user request or approved plan
3. Test or verification results, if any
4. Root cause for bug fixes, if known

If any detail is unclear, inspect the files or ask the user. Never invent history.

## Default Output Location

Write to `CHANGELOG.md` at the project root unless the project already uses another dedicated history file.

If `CHANGELOG.md` does not exist, create it with:

```md
# Changelog
```

## Entry Format

Insert the newest entry near the top of the file, below the title if present.

```md
## [YYYY-MM-DD] - <short title>
- Mode: `<MVP|MAINTENANCE>`
- Level: `<M0|M1|M2|L0|L1|L1+|N/A>`
- Summary:
  - <completed change 1>
  - <completed change 2>
- Verification:
  - <tests, review, or manual validation>
- Root Cause:
  - <required for bug fixes; omit if not applicable>
- References:
  - <plan/spec/PR/issue path if relevant>
```

## Process

### Step 1: Confirm scope

Identify what actually shipped in this task. Prefer concrete nouns and verbs over vague summaries.

### Step 2: Classify the work

Choose the best fit:

- `MVP` for new features, new modules, or larger design-led work
- `MAINTENANCE` for fixes, tweaks, optimization, refactors, and iterative improvements

Add a level only if it is known from the active workflow. Otherwise use `N/A`.

### Step 3: Write a factual summary

Summaries must describe completed work, not intention.

Good:

- Added invoice export action to the billing dashboard
- Fixed stale session state after logout redirect

Bad:

- Improved system
- Updated some files
- Refactored code

### Step 4: Capture verification

Record the strongest evidence available:

- Automated tests run
- Build or lint results
- Manual UI validation
- Code review completed

If verification did not happen, say so plainly instead of implying success.

### Step 5: Capture root cause when relevant

For bug fixes, include one short statement explaining why the bug happened.

Example:

```md
- Root Cause:
  - Logout state was cached in the client store and not cleared during route transition.
```

### Step 6: Update the file

Add the new entry in reverse chronological order. Preserve existing history unless the user asks to rewrite it.

## Quality Bar

Every entry should be:

- Specific enough for a teammate to understand later
- Honest about what was and was not verified
- Scoped to one delivery unit
- Linked to supporting design or plan docs when useful

## Common Mistakes

**Writing intent instead of result**
- Wrong: "Implement payment retry"
- Right: "Added payment retry flow for failed card charges"

**Hiding uncertainty**
- Wrong: "Verified"
- Right: "Manual validation completed; automated tests not run in this task"

**Overwriting previous history**
- Keep existing entries and prepend the new one

**Copying git commit text blindly**
- Rewrite commit fragments into a clear changelog summary
