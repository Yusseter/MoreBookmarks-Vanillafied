# Project Working Rules

## Resume And Scope

- Read `.codex/TODO.md` for the current task and return point. Search only the relevant sections of `.codex/memory/project_memory.md` for prior decisions; consult linked plans and reports as needed.
- Use the conversation and recorded evidence before repeating completed work. Recheck facts when the relevant files, revisions, configuration, or user observations have changed.
- A question or discussion permits relevant read-only verification, not implementation. Dated files in `.codex/prompts/` are the user's local request archive; use one as an active task only when the user selects it, and check time-sensitive claims.
- Keep the agreed task order. When a side task becomes necessary, record why and where to return in TODO. Update task status at meaningful completion or handoff points, with evidence and the next action.
- Communicate briefly in Turkish. Explain decisions that affect scope or behavior. Ask the user when their knowledge can resolve uncertainty more efficiently, and ask about consequential choices that existing instructions do not settle.

## Sources And Ownership

- The live mod is `BookmarksGit/`. Resolve the upstream and vanilla roots from `Yusseter-MBP-Development.code-workspace`; treat them as reference sources unless edits there are explicitly requested.
- Follow `.codex/works/README.md` for tools, permanent inputs, generated outputs, reports, and archives. Use existing tools and directories before adding new ones.
- Preserve user-owned `map_data_sources/manual_sources/` content and `pipeline_inputs/title_relations/curated_title_relations.csv` under `.codex/works/`; generators must not overwrite them.
- The user's pending `BookmarksGit/fonts/fonts.font` edit is on hold. Do not modify or commit it without a new instruction.
- Keep project memory separate from AGENTS.md and skills. Read memory when relevant; update it only when requested. TODO is the operational task record, and plans retain historical detail.

## CK3 Evidence And Skills

- Use the available `ck3-modding` and `ck3-modding-wiki` skills for relevant CK3 work. Check the installed game's corresponding references when versions or engine behavior matter. If a skill is unavailable, disclose that and use explicit source evidence.
- General CK3 knowledge belongs in reusable skills; project decisions, IDs, paths, and work status belong in project records. New lessons need a source, applicable version or context, and a distinction between static evidence and in-game confirmation.
- Repository skills belong in `.agents/skills/<skill-name>/SKILL.md`. Do not copy entire installed skills into this repository just to duplicate availability; decide the scope of a new or shared skill when implementing that task.
- Distinguish Yusseter adaptation errors, inherited upstream errors, intentional differences, false positives, and unresolved runtime behavior. Keep shared upstream errors recorded and deferred until the user resumes that cleanup phase.
- Audit tools support mod work. Change them when a demonstrated limitation prevents a reliable answer; state that reason and keep the original task visible. Do not regenerate the full audit chain for unrelated documentation work.
- Validate the affected behavior and dependencies. A clean static report does not prove runtime UI behavior; retain existing user test evidence and request only the missing checks needed for the current change.

## Files And Git

- Write new maintained project documentation, TODO entries, README guidance, plans, and skills in English; communicate with the user in Turkish. Preserve historical Turkish notes and personal prompt text. Ask only when a document's audience or an explicit request leaves its language unclear.
- Preserve encoding, CK3 localization BOMs, meaningful whitespace, and Turkish prose. Avoid mass reformatting or translating historical notes as part of another task.
- Use concise English names for new paths and the plan naming rules in `.codex/plans/README.md`. A rename must preserve content and update active consumers.
- When commits are authorized, group them by purpose, stage explicit paths or hunks, and inspect the staged diff. Use the configured Git identity and descriptive English summary/body text, without an AI co-author line or a required conventional prefix.
- Use the user's supplied commit examples as references for tone and useful detail. Do not infer a fixed paragraph count, layout, or mandatory Copilot standard; describe the actual staged change.
- Continue an authorized commit sequence without asking again for each commit. Leave unrelated WIP and unresolved decisions outside it. Do not push; the user reviews and pushes.
