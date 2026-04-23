# /commit

Create a well-structured commit for staged changes.

## Steps
1. Run `git diff --cached --stat` to see staged changes
2. If nothing is staged, run `git add -p` to interactively stage changes
3. Analyze the diff to understand the change
4. Generate a commit message following this project's convention:
   - Format: `descriptive message`
5. Present the message for confirmation
6. Commit with the approved message

## Constraints
- One logical change per commit
- If staged changes cover multiple concerns, suggest splitting
- Never use generic messages like "update" or "fix stuff"
