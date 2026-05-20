# suno-assistant Feature Delivery

Use this skill for issue-driven implementation work in suno-assistant when the task is to deliver one or several GitHub issues end to end.

Read first:
- `AGENTS.md`
- `README.md`
- `docs/INDEX.md`
- `docs/AGENT_CONTEXT.md` when present

Use the GitHub workflow as the default delivery path for functional changes.
If the user explicitly requests a direct push to `main` without a PR, treat that as an override to this default workflow rather than inferring a PR anyway.

Workflow:
1. Start on `main` and pull `origin/main`.
2. If the work is tied to a GitHub issue, read the issue with the GitHub CLI before implementing:
   - use `gh issue view <number>` to read the issue body
   - use `gh issue view <number> --comments` when comments or clarifications may affect scope
   - do not rely only on branch names, PR titles, or secondhand summaries when the issue itself is available
3. Create a dedicated Git worktree from fresh `main`. Do not implement feature work directly in the primary repo checkout.
4. Create a dedicated branch in that worktree using repo naming rules:
   - `feature/...` for features
   - `fix/...` for bug fixes
   - `docs/...` for docs-only work
   - include the GitHub issue number near the front when relevant, for example `feature/123-api-cleanup`
5. Implement the issue scope in that worktree.
6. Document architecture usage and explain how the change works.
7. Update docs and Mermaid/context docs when schema, API surface, control flow, or data flow changes.
8. Run targeted tests, then `pre-commit`, and fix failures before commit.
9. Commit with a conventional message, push the branch, and open a PR that closes the issue.
10. Wait for CI and fix failures until green.
11. Once CI is green, request an external review by adding `@codex review` or the repository's equivalent review trigger on the pull request.
12. While waiting for the review to arrive, review your own PR and leave a self-review comment that covers the main change, primary risks, and any test or verification gaps you still see.
   - scale self-review depth to implementation risk
   - for high-risk changes such as background automation, queue processing, task lifecycle, API or CLI concurrency, locks, retries, sync high-water marks, stale-run cleanup, or cancellation paths, do not stop at happy-path behavior and basic observability
   - in high-risk self-review, explicitly challenge failure modes such as:
     - partial success followed by a later side-effect failure
     - retry or idempotency after state or high-water marks advance
     - cancellation at awaited boundaries, including `asyncio.CancelledError`
     - stale state versus long-running live work
     - read-before-act races in multi-process deployments
     - interaction between automation, API, CLI, and worker entry points
     - queue row state transitions and terminal-update preconditions
     - lock acquisition and release behavior, including pool starvation and request shutdown
   - if repeated risks fall into the same category, pause and audit the whole category before asking for another review
13. Wait up to five minutes for the external review to arrive. If no review is present after five minutes, skip the external review requirement and continue the process.
14. Read the review carefully and participate in the feedback loop:
   - inline review comments are not visible in `gh pr view --json reviews,comments`; that command is not a sufficient review audit
   - always audit review threads with GraphQL before deciding there are no actionable findings:
     ```bash
     gh api graphql \
       -f owner=<owner> \
       -f repo=<repo> \
       -F number=<pr-number> \
       -f query='query($owner:String!, $repo:String!, $number:Int!) {
         repository(owner:$owner, name:$repo) {
           pullRequest(number:$number) {
             reviewThreads(first:100) {
               nodes {
                 id
                 isResolved
                 isOutdated
                 comments(first:20) {
                   nodes {
                     id
                     author { login }
                     body
                     path
                     line
                     url
                   }
                 }
               }
             }
           }
         }
       }'
     ```
   - treat any review-thread comment with an actionable finding as requiring an inline reply, even if the top-level review body is generic
   - as soon as a review lands, audit the review threads and reply in-thread before starting the next round of fixes
   - do not treat review comments as a private TODO list while leaving the GitHub threads unanswered; acknowledge the finding in-thread first, even if the reply is only that you are investigating or plan to address it in the next commit
   - reply to each review comment directly as a reply to that comment thread, not as a new top-level PR comment
   - do this for every review round, including follow-up reviews after additional commits
   - after each new review lands, explicitly audit the PR review threads and identify any new unresolved findings before deciding the PR is ready
   - before writing more code for review feedback, make sure every current finding already has an inline reply with a clear disposition such as fixed, investigating, deferred, declined, or not applicable
   - after replying inline, use this cadence for review feedback:
     - receive the review batch
     - reply inline immediately
     - pause
     - do a full self-audit across the whole class of bugs
     - fix the class, not just the exact comment
     - push one coherent hardening commit
     - request review again
   - avoid a tight loop of small fix, review, small fix, review
   - when several findings point at one risk class, consolidate the fix so the next review validates the model rather than discovering the next adjacent failure
   - when a finding is fixed, reply in-thread with the resolution and the commit that addressed it
   - when a finding is deferred or declined, reply in-thread with the reason so the thread has an explicit disposition
   - if the feedback is reasonable, prefer fixing it in the same PR, rerun validation, and push updates
   - only defer review feedback to a follow-up when there is a good reason not to expand the current PR, such as materially increased scope, materially increased complexity, a riskier change, or a case that needs more careful design work
   - if the feedback should be deferred, create a follow-up issue and explain why it is not being fixed in the current PR
   - if the feedback is not applicable, document why in the PR so the resolution is explicit
15. After responding to review and your self-review findings, leave the required decision comment describing what was fixed now, deferred, or not done.
16. If a follow-up issue is needed, create it with a title starting `[followup]`.
17. Merge the PR.
18. Return to the primary checkout, pull fresh `origin/main`, clean up the feature branch, remove the merged worktree, and update any session notes if the repository uses them.

Guardrails:
- PR by default; direct push only when the user explicitly asks for it.
- Never skip `pre-commit` and never use `--no-verify`.
- Never change the coverage target without an explicit user request.
- Do not merge immediately after CI goes green; request external review, wait up to five minutes, and handle the feedback loop before merge. If no review arrives within five minutes, skip it and continue.
- The implementing agent must still do its own self-review even when external review is requested.
- Once review lands, reply in-thread before diving into more implementation work.
- Before merge, run the GraphQL review-thread audit above and verify that every review finding has an inline reply and an explicit disposition, especially after follow-up commits and re-reviews.
- Before merge, do not rely on top-level PR comments or `gh pr view --json reviews,comments` as proof that review feedback was handled.
- Keep the primary repo checkout as the clean control checkout; do feature coding inside the dedicated worktree only.
- Remove merged worktrees promptly so stale branches and stale directories do not accumulate.
