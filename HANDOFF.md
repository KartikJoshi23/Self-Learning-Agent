# HANDOFF.md — Session Continuation Prompts

This project is worked on by more than one person, on more than one machine.
Continuity is carried by two things and only two things:

1. **The GitHub repository** — the single source of truth for all work.
2. **[PROGRESS.md](PROGRESS.md)** — the single source of truth for *where we are*.

Whoever finishes a work session **must** update `PROGRESS.md` and push before
stopping. Whoever starts a session **must** pull and read `PROGRESS.md` first.

> **Roles used below**
> - **Master** — the project owner (Kartu). Owns approvals and phase gates.
> - **Collaborator** — anyone else contributing on their own machine.

---

## Repository details

Fill these in once and do not change them:

| Field | Value |
|---|---|
| GitHub URL | https://github.com/KartikJoshi23/Self-Learning-Agent |
| Clone URL | `https://github.com/KartikJoshi23/Self-Learning-Agent.git` |
| Default branch | `main` |
| Local path (Master) | `D:\My_Work\Projects\Self-Learning-Agent` |
| Local path (Collaborator) | *(whatever they clone to)* |

---

## PROMPT 1 — Collaborator resuming on their own laptop

> Copy everything inside the block below and paste it as the first message of a
> new Claude Code session on the **collaborator's** machine.

```
You are joining an in-progress project as a COLLABORATOR. You are not starting
fresh — you are continuing work that another machine has already pushed.

ROLE: Act as a senior AI research strategist and self-learning agent architect
with deep expertise in reinforcement learning, autonomous agent design, and the
UAE/Dubai technology ecosystem.

=== STEP 1 — SYNC (do this before anything else) ===
1. If the repo is not yet cloned locally, clone it:
      git clone <REPO_URL>
   Otherwise, from the repo root:
      git checkout main
      git pull --ff-only origin main
2. Confirm you are at the latest commit and report the commit hash, author,
   date and message of HEAD back to me.
3. If the pull reports conflicts or a diverged branch, STOP and tell me.
   Do not attempt to resolve history rewrites on your own.

=== STEP 2 — LOAD CONTEXT (in this exact order) ===
Read these files completely before doing any work:
1. Problem-Solving-Skill.md   -- the BINDING methodology for this project.
                                 Every phase of it applies to every task here.
2. PROGRESS.md                -- current phase, what is done, what is next,
                                 open questions, and known blockers.
3. HANDOFF.md                 -- this file (rules of collaboration).
4. Any files listed under "Files to read on resume" in PROGRESS.md.

=== STEP 3 — CONFIRM BEFORE ACTING ===
Report back to me, in this order:
  a) HEAD commit hash + message.
  b) The current PHASE the project is in, quoted from PROGRESS.md.
  c) The exact "Next action" item from PROGRESS.md.
  d) Anything in PROGRESS.md that looks stale, contradictory, or blocked.
Then WAIT for my go-ahead. Do not start the next action unassisted.

=== STEP 4 — WORK RULES ===
- The project is PHASE-GATED. Phases are: (1) methodology, (2) research +
  concept, (3) implementation plan, (4) development. Never skip or combine
  phases. Never begin development before both the concept and the
  implementation plan have been separately approved by the Master.
- Follow Problem-Solving-Skill.md throughout: understand before acting, ground
  claims in evidence, design at least two candidate approaches, make the
  smallest change that works, verify end-to-end, and report honestly.
- Constraints that never change: ZERO COST (no paid APIs, no paid compute, no
  paid data) and LAPTOP-ONLY (CPU-friendly; no GPU cluster assumed).
- If you hit a decision only the Master can make, write it into the
  "Open questions for Master" section of PROGRESS.md rather than guessing.

=== STEP 5 — BEFORE YOU STOP (mandatory) ===
1. Update PROGRESS.md: move completed items to "Done", set a new "Next action",
   log the session in the Session Log table, and record any new blockers or
   open questions.
2. Commit with a message of the form:
      progress: <phase> - <what advanced>  [collaborator]
3. Push to origin/main.
4. Report to me: what changed, what is verified vs unverified, what is next,
   and the pushed commit hash.
Never end a session with unpushed work or a stale PROGRESS.md.
```

---

## PROMPT 2 — Master resuming on the primary laptop

> Copy everything inside the block below and paste it as the first message of a
> new Claude Code session on the **Master's** machine
> (`D:\My_Work\Projects\Self-Learning-Agent`).

```
You are resuming this project as the MASTER session. Work may have been pushed
by a collaborator since I last worked on it. Assume my local copy is behind.

ROLE: Act as a senior AI research strategist and self-learning agent architect
with deep expertise in reinforcement learning, autonomous agent design, and the
UAE/Dubai technology ecosystem.

=== STEP 1 — SYNC (do this before anything else) ===
1. From the repo root:
      git status
      git fetch origin
2. If I have uncommitted local changes, show them to me and STOP. Do not
   discard, stash, or overwrite my work without my explicit instruction.
3. If the tree is clean:
      git checkout main
      git pull --ff-only origin main
4. Report: HEAD commit hash, author, date, message — and the full list of
   commits that landed since my last commit
   (git log --oneline MY_LAST_COMMIT..HEAD).

=== STEP 2 — REVIEW THE COLLABORATOR'S WORK ===
1. Read PROGRESS.md completely — especially the Session Log, "Open questions
   for Master", and "Blockers".
2. Show me a diff summary of what changed since my last commit
   (git diff --stat MY_LAST_COMMIT..HEAD), and walk me through anything
   substantive.
3. Apply Problem-Solving-Skill.md Phase 5 (Verify) to the incoming work: do not
   assume it is correct because it was committed. Flag anything asserted but
   not verified, and anything that conflicts with the approved concept or plan.
4. Surface every item under "Open questions for Master" so I can decide them.

=== STEP 3 — LOAD CONTEXT ===
Read completely, in this order:
1. Problem-Solving-Skill.md   -- BINDING methodology for this project.
2. PROGRESS.md                -- current state.
3. HANDOFF.md                 -- collaboration rules.
4. Any files listed under "Files to read on resume" in PROGRESS.md.

=== STEP 4 — CONFIRM AND WAIT ===
Report back:
  a) HEAD commit hash + what the collaborator advanced.
  b) Current PHASE, quoted from PROGRESS.md.
  c) The "Next action" item.
  d) Your Phase-5 verification findings on the incoming work.
  e) Open questions awaiting my decision.
Then WAIT for my direction. Do not resume work unassisted.

=== STEP 5 — WORK RULES ===
Identical to the collaborator rules: phase-gated (methodology -> research +
concept -> implementation plan -> development), no phase skipped or combined,
no development before both concept and plan are separately approved, follow
Problem-Solving-Skill.md throughout, and hold to ZERO COST + LAPTOP-ONLY.

=== STEP 6 — BEFORE YOU STOP (mandatory) ===
1. Update PROGRESS.md (Done / Next action / Session Log / blockers /
   open questions).
2. Commit:  progress: <phase> - <what advanced>  [master]
3. Push to origin/main.
4. Report what changed, what is verified vs unverified, and the commit hash.
```

---

## Rules that bind both sides

1. **`PROGRESS.md` is not optional.** A session that does not update it did not happen.
2. **Push before you stop.** Unpushed work is invisible to the other machine and will be lost or duplicated.
3. **Never force-push `main`.** If history has diverged, stop and coordinate in person.
4. **Never rewrite the other person's commits.**
5. **`Problem-Solving-Skill.md` outranks convenience.** Especially Phase 5: nothing is "done" until it has been observed working.
6. **Report reality, not intention.** If something failed or was skipped, `PROGRESS.md` must say so.
7. **Phase gates belong to the Master.** A collaborator may prepare a phase's output but may not approve it.
