# suno-assistant Feature Design

Use this skill when the task is not to implement a suno-assistant feature yet, but to design it well enough that developers can execute it cleanly.

Read first:
- `AGENTS.md`
- `README.md`
- `docs/INDEX.md`
- `docs/AGENT_CONTEXT.md` when present
- `references/github_issue_mockup_screenshots.md` when the task includes mockup screenshots or GitHub issue image uploads

Default stance:
- act like a system architect translating product intent into an implementation-ready engineering plan
- keep solutions as simple as possible, but add complexity where the problem genuinely needs it
- do not fake certainty; if important requirements or tradeoffs are unclear, ask for clarification

Use this skill for:
- turning a rough feature request into a concrete design
- refining a draft GitHub issue into an implementation-ready issue body
- creating a new GitHub issue when no issue exists yet
- reviewing references such as related issues, PRs, screenshots, docs, or code paths to shape the design
- creating lightweight HTML and CSS mockups for proposed web UI changes when a visual guide would reduce ambiguity
- capturing screenshots from those mockups or from browser tooling when available so the issue can include concrete visual direction
- using authenticated browser automation when available to open local mockups, capture screenshots, and upload those screenshots directly into GitHub issues or PRs
- writing phased implementation plans, validation plans, and explicit open questions before coding starts

Workflow:
1. Start by understanding the request:
   - identify the user problem, desired outcome, and any stated constraints
   - note references provided by the requester such as issue numbers, PRs, screenshots, pages, or files
2. Gather project context before proposing solutions:
   - read `AGENTS.md`, `README.md`, `docs/INDEX.md`, and `docs/AGENT_CONTEXT.md` when present
   - read only the relevant docs and code paths needed for the feature
   - if a GitHub issue already exists, read it with `gh issue view <number>`
   - use `gh issue view <number> --comments` when comments may affect scope or decisions
   - if related PRs or issues are referenced, read those too before finalizing the design
3. Clarify uncertainty early:
   - if important requirements, tradeoffs, or acceptance criteria are unclear, ask the requester before locking the design
   - if screenshots or visual references are provided, inspect them rather than guessing
4. Design the feature at the right level:
   - define the problem and why the change is needed
   - describe the proposed user-facing behavior
   - identify the affected architecture, APIs, data flow, storage, UI states, background jobs, or operational paths
   - call out non-goals when they help keep the scope controlled
   - prefer the smallest design that solves the actual problem cleanly
   - when the request includes a meaningful UI change, decide whether a mockup or screenshot would make the plan clearer
5. Turn the design into an implementation plan developers can execute:
   - break the work into ordered steps or phases
   - include validation expectations such as tests, docs updates, migration handling, and operational verification when relevant
   - surface risks, edge cases, follow-ups, and rollout concerns explicitly
   - for high-risk work, split the design into explicit invariants before coding
   - high-risk work includes background automation, queues, schedulers, workers, sync pipelines, task lifecycle, API or CLI concurrency, locks, retries, stale cleanup, cancellation-sensitive flows, schema migrations, and operational control paths
   - useful invariants include:
     - no overlapping execution across all entry points that can start the same work
     - no synced or externally observed delta can be lost before downstream enqueue or persistence
     - no stale worker or run can terminally update state after a newer pending trigger exists
     - cancellation never loses claimed work
     - stale cleanup never kills live long-running work
     - locks must not consume the same constrained resource pool needed by protected work
   - for these features, include a failure-mode matrix and validation plan that directly tests the invariants
   - if UI mockups are created, describe how they map to the implementation plan rather than leaving them as disconnected visuals
6. Write the GitHub issue:
   - if an issue already exists, update its description so the issue body becomes the current source of truth
   - if no issue exists, create a new issue with a clear title and full body
   - preserve useful existing context instead of overwriting it carelessly
   - when a mockup exists and browser automation is available, prefer opening the mockup in the browser, taking screenshots, and uploading those images into the GitHub issue or PR instead of pasting raw HTML or CSS
7. Before finishing:
   - if there are unresolved design gaps, include explicit open questions and ask the requester for feedback
   - make sure the issue is specific enough that an implementing agent can pick it up without needing to rediscover the architecture

UI mockup guidance:
- Use mockups when the request changes web-app layout, controls, information hierarchy, empty states, detail pages, dialogs, or operator workflows.
- Prefer lightweight HTML and CSS mockups over heavy implementation when the goal is visual clarification rather than shipping UI code.
- If browser or Playwright-style tooling is available, use it to inspect the current UI and capture screenshots of mockups or live references.
- Store GitHub-authenticated Playwright browser state at `.playwright-mcp/auth/github-storage-state.json` so the browser session can be reused for issue and PR updates without committing secrets to the repo.
- If authenticated GitHub access is available in that browser session, complete the loop there: open the local mockup, capture the screenshots, save them, then edit the GitHub issue or PR and upload the images so they render inline.
- When browser MCP is not sufficient for reliable click and file-upload automation, use `scripts/github_mockup_issue_assets.py` from this skill. It captures selector-based screenshots from a local mockup, uploads them through the authenticated GitHub session, and writes both a manifest and a Markdown snippet for the issue body.
- The proven issue-upload path is the issue or PR comment form. Use the textarea selector `textarea[placeholder="Use Markdown to format your comment"]` and the `Add files` button to upload images.
- GitHub inserts uploaded images into the textarea as HTML `<img ... src="https://github.com/user-attachments/assets/...">` tags rather than Markdown. Extract the `user-attachments` URLs and use those URLs in the main issue body or PR description.
- Prefer updating the main issue body after the assets exist instead of leaving the screenshots only in a comment. Replace raw mockup source with concise captions plus the uploaded images.
- Do not treat GitHub issue bodies as a place to paste full mockup source; GitHub images plus concise Markdown context are the preferred deliverable.
- Keep mockups close to the existing product visual language unless the requester asks for a larger redesign.
- Treat mockups as design aids: they should clarify states, actions, and structure, not silently expand feature scope.

Preferred issue structure:
- Problem
- Goal
- Non-goals
- Current context
- Proposed design
- Invariants for high-risk work
- Failure-mode matrix for high-risk work
- Visual guide or mockups
- Implementation plan
- Validation
- Risks or edge cases
- Open questions

Guardrails:
- Design from the existing architecture instead of inventing a parallel system without reason.
- If the feature changes schema, API surface, control flow, or data flow, say so explicitly in the plan.
- If the feature affects operations, deployment, worker behavior, CI, or observability, include those consequences in the issue body.
- If the feature includes UI work and a mockup would meaningfully reduce ambiguity, include a visual guide in the issue body or issue comments.
- If the request is still too ambiguous after reading the references, stop and ask for clarification rather than producing a vague plan.
- Do not jump into implementation when the task is clearly design and planning.

Output expectations:
- Produce an implementation-ready GitHub issue body, not just loose brainstorming notes.
- Make tradeoffs and assumptions explicit.
- When a phased rollout is safer than a single large change, say so and structure the plan accordingly.
- When mockups are included, explain what they are intended to communicate and what is still left for implementation judgment.
