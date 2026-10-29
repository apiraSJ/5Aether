# ContextCal Technical Debt

## Level 3 (existing, not touched in this pass)

| Item | Impact | Condition to revisit |
|---|---|---|
| `resolve_review("reject")` via `delete()` + `ON DELETE CASCADE` removes review row; spec expects REJECTED row to remain | Audit trail loses rejected review state in current flow | If acceptance requires visible REJECTED rows; consider resolve-before-delete or schema change |
| `task.extract` dedupes by `sha256(text)` permanently | If rejected and user wants to re-analyze same text, returns deduplicated result | Change to include draft id/session or TTL-based dedup |
| `needs_confirmation` items leak to `/tasks` and `/calendar` (list not filtered) | Unconfirmed items can appear in web views if created via CLI | Filter by `internal_status='confirmed'` in read paths or route to review only |
| Plugin uses `try/except: pass` in places | Swallows errors | Review plugin error handling separately |

## Limitations (v1)

| Item | Notes |
|---|---|
| DraftStore in-memory only | Restart/multi-process loses drafts and confirmation state. Not a source of truth. |
| No cross-draft dedup with existing tasks | Confirming can create duplicates; warn or dedupe in future. |
| Numeric dates without year/context limited | `14/11` requires context to avoid false positives. |
| R13 coverage | Supports `ถึง HH:MM`, `- HH:MM`, `เป็นเวลา N ชั่วโมง`, `อีก N นาที`. Cross-midnight ranges marked ambiguous (no guess). Duration without start marked missing time. |
| HTTP idempotency | Token is internal; API should map `Idempotency-Key` to begin_confirm. |

## Resolved in Acceptance Pass

| Item | Resolution |
|---|---|
| A1 evidence failure | `attach_evidence` no longer swallowed; exception propagates and batch rolls back |
| A2 end_at | Implemented for ranges/durations with guards |
| A3 test strictness | Restored strict assertions for draft tests |
| A4 selection conflict | `selection_fingerprint` + `ContextCalConflictError` on mismatch |
