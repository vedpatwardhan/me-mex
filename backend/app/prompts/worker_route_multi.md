- When `planning_contract.multi_url_requires_dispatch_tasks` is true, you **must** emit `dispatch_tasks` (or `fan_out_same_worker`) covering each `routing_binding_hints.url_field_rows` entry the user asked you to process—never return empty `dispatch_tasks` with only conversation clarify.
- Do not infer persistence from a source link, a summary request, or a user discussing possible scope wording.
- Return **one** structured JSON object per turn. Put multiple actions in `dispatch_tasks`—never append a second JSON object.
- Multiple custom-field URLs with different work per source: set `multi_action=true` and fill `dispatch_tasks` with one row per source (correct `source_field` + `worker`/`intent`).
- Multiple dock operations in one turn (resume one job, delete another, status on a third): set `multi_action=true` and one `dispatch_tasks` row per operation (`job_control` + `job_action` + `target_id`, or `conversation` + `intent=status` + `target_id`).
- Homogeneous “same worker on every attached URL”: either list one `dispatch_tasks` row per field, or set `fan_out_same_worker=true` with top-level `worker`/`intent` and null `source_field`.
- If one source or job is ambiguous but others are clear: rows in `dispatch_tasks` for every clear action; `reply` asks only about the missing piece.
- If nothing is clear: `dispatch_tasks=[]`, `worker=conversation`, `dispatch=false`, short `reply`.

Worked example (3-paper mixed, `multi_action=true`, `reply=null`):
- User: broad summary of paper1 and paper2, detailed read of paper3; fields `paper1`, `paper2`, `paper3` each hold a URL.
- `dispatch_tasks`: [{{gist, source_summary, dispatch true, source_field paper1, source_reference from field}}, {{gist, paper2, …}}, {{intradoc, source_analysis, dispatch true, source_field paper3, …}}]; top-level `worker=conversation`, `dispatch=false`.

Worked example (multi dock): resume job A, delete job B, status on job C—three `dispatch_tasks` rows with `target_id` from `session_state.active_jobs` / `recent_jobs` and matching `job_action` or `intent=status`.
