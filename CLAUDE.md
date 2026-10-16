# Claude guidance

Follow existing repository documentation and the user's authorised scope.

<!-- project-coordination:reporting-v2:start -->
## Shared progress reporting

This repository uses `project-coordination/v1`. At the start of substantive work,
read `.coordination/README.md`, existing task breadcrumbs and the shared claim.
Run `python3 .coordination/report.py requests` to read queued work from this
repository's current GitHub default branch, even in a stale checkout. Check again
before finishing or handing over and at material work checkpoints. This applies
equally to Codex and Claude. For a queued request, retain its task_id, roadmap_id,
milestone_ids, exact scope and criteria when starting; publish the shared claim
before implementation. A claim acknowledges pickup; another active actor means
leave it to that actor. Do not silently re-claim completed or cancelled work.
Before changing code, run `.coordination/report.py start` with the exact task UUID,
a unique actor UUID for this chat/run, title and scope. Start only after it exits
successfully and confirms the claim on GitHub. Another active actor means wait;
never duplicate, steal or silently expire a claim. Preserve IDs through handover.

Use the reporter for substantive progress, blockers and outcomes, including local
and unpushed work. Report at take-on, material changes, before handover/ending and
when the outcome changes; do not publish polling noise. Only request Robert's
input for a specific decision, approval, access, file, token or physical action.
Agent review, testing and ordinary implementation are agent work.

Publishing sanitised coordination metadata to the private coordination repository
is authorised separately from publishing project code. Never push implementation,
secrets, personal/case/financial/medical data or private local paths through this
reporting rule. Done assertions require exact-scope evidence; commit, delivery and
process exit alone do not prove completion. Read the reporter receipt; on failure,
retain the local breadcrumb and report publication uncertainty. Never claim sync.
<!-- project-coordination:reporting-v2:end -->
