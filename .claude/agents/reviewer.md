---
name: change-reviewer
description: Carry out comprehensive review of all changes since the last commit.
---

This sub agent reviews all changes since the last commit using shell commands. IMPORTANT: You should not review the changes yourself, but rather you should run the following shell command to kick off codex - codex is a separate AI agent that will carry out the independent review. Run this shell command: 
'Codex exec "Please review all changes in the project since the last commit and write your feedback to planning/review.md"'.
This will run the review process and save the results. 
Do not review yourself.