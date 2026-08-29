\---

name: problem-solving

description: A rigorous, end-to-end methodology for solving any technical problem - analyzing it, designing a solution, implementing it, and verifying correctness before declaring it done. Use this skill whenever the user asks to fix a bug, build a feature, debug unexpected behavior, refactor code, or solve any non-trivial technical task, even if they don't explicitly ask for a "process" or "methodology". Especially use it when the problem is vague, multi-step, or when a previous attempt at the problem failed.

\---

\# Problem-Solving Methodology

This skill describes how to take a problem from first contact to a verified, correct solution. The core idea: most bad solutions come from solving the wrong problem or from declaring victory without proof. Every phase below exists to prevent one of those two failures.

\## Phase 1 - Understand the problem before touching anything

Resist the urge to start writing code immediately. Time spent here is the cheapest time in the whole process; a misunderstanding caught now costs minutes, the same misunderstanding caught after implementation costs hours.

1\. \*\*Restate the problem in your own words.\*\* What is the observed behavior? What is the expected behavior? What is the gap between them? If you cannot state all three precisely, you don't understand the problem yet.

2\. \*\*Separate symptoms from the problem.\*\* "The page is blank" is a symptom. The problem might be a failed API call, a rendering error, or a CSS issue. Never fix a symptom directly until you know what produces it.

3\. \*\*Identify the real goal.\*\* Users often ask for a specific fix ("increase the timeout") when the underlying goal is different ("stop requests from failing"). Solve for the goal, and flag it when the requested fix and the goal diverge.

4\. \*\*Collect the constraints.\*\* Language, framework, existing conventions, performance requirements, backwards compatibility, what must NOT change. A solution that ignores constraints is not a solution.

5\. \*\*Ask only the questions you cannot answer yourself.\*\* Read the code, run the program, and check the logs before asking the user anything. Reserve questions for genuine decisions - trade-offs only the user can make.

\## Phase 2 - Investigate and analyze

Ground every belief in evidence from the actual system, not from assumptions or memory.

1\. \*\*Read the relevant code first-hand.\*\* Do not guess how a function behaves from its name - open it. Trace the actual execution path from entry point to the point of failure or the point of change.

2\. \*\*Reproduce the problem\*\* (for bugs). A bug you can reproduce on demand is half-solved. A bug you cannot reproduce is not yet understood - keep narrowing conditions until you can trigger it reliably.

3\. \*\*Locate the root cause, not the first suspicious thing.\*\* Ask "why" repeatedly: the button does nothing → the handler throws → the state is undefined → the fetch never resolved → the URL is wrong. Fix the deepest "why" that is actually in scope.

4\. \*\*Map the blast radius.\*\* Before changing anything, find every caller and consumer of the code you're about to touch (search for usages, check exports, check tests). A change is only safe when you know everything it affects.

5\. \*\*Write down what you now know.\*\* State the root cause or the requirements as a falsifiable claim ("the race happens because X runs before Y"). If evidence later contradicts it, go back - do not push forward on a broken theory.

\## Phase 3 - Design the solution

Design is choosing among alternatives on purpose, not implementing the first idea that comes to mind.

1\. \*\*Generate at least two candidate approaches\*\* for anything non-trivial. Even a quick mental sketch of "patch it here" vs. "restructure this" reveals trade-offs that a single-track mind misses.

2\. \*\*Evaluate candidates against the constraints\*\* from Phase 1: correctness, simplicity, consistency with the existing codebase, performance, and how easy each is to verify and to undo. Prefer the simplest design that fully solves the problem - complexity must earn its place.

3\. \*\*Follow the codebase, not your habits.\*\* Match existing patterns, naming, error handling, and file structure. A technically correct solution that fights the codebase's conventions creates future problems.

4\. \*\*Design for verifiability.\*\* While designing, decide how you will prove the solution works. If a design is hard to test or observe, that is a mark against the design itself.

5\. \*\*Break the work into ordered, checkable steps.\*\* Each step should leave the system in a working (or at least buildable) state where possible, so problems surface at the step that caused them.

6\. \*\*State the plan before executing it\*\* when the change is significant, so the user can redirect before effort is spent.

\## Phase 4 - Implement

1\. \*\*Make the smallest change that fulfills the design.\*\* Do not refactor unrelated code, rename things opportunistically, or "improve" code you weren't asked to touch - every extra change widens the blast radius and muddies review.

2\. \*\*Work in increments and check as you go.\*\* After each meaningful step, build/run/lint. Catching an error immediately after introducing it is trivially easy; catching it after ten more changes is archaeology.

3\. \*\*Handle the edges, not just the happy path.\*\* Empty inputs, nulls, error responses, concurrent access, boundary values. Ask of every function you write: "what inputs would break this?" - then handle or explicitly reject them.

4\. \*\*Keep the code honest.\*\* No swallowed errors, no magic values, no commented-out code left behind. Add a comment only where the code cannot explain itself (a non-obvious constraint or a deliberate trade-off).

5\. \*\*When something unexpected happens, stop and understand it.\*\* An "it works now but I don't know why" state is a debt that will be repaid with interest. Return to Phase 2 rather than piling changes on top of a mystery.

\## Phase 5 - Verify correctness

A solution is not correct because it compiles, and not correct because it "should work". It is correct when you have observed it doing the right thing. This phase is not optional.

1\. \*\*Exercise the actual change end-to-end.\*\* Run the program, load the page, call the endpoint, execute the script - whatever the real usage path is. Static inspection and passing builds are necessary but never sufficient.

2\. \*\*Verify against the original problem statement.\*\* Go back to Phase 1's observed-vs-expected gap and confirm the gap is closed. It is surprisingly easy to fix an adjacent problem and forget the original one.

3\. \*\*Test the edges you handled.\*\* If you handled empty input, feed it empty input and watch it behave. An untested edge case handler is just a guess with extra code.

4\. \*\*Check for regressions in the blast radius.\*\* Re-exercise the callers and features you mapped in Phase 2. Run the existing test suite if there is one. The most common failure mode of a fix is breaking something nearby.

5\. \*\*Try to falsify your own solution.\*\* Actively look for a way it could still be wrong: a race, a second code path with the same bug, a cached value, an environment difference. The goal is to find the flaw before the user does.

6\. \*\*If verification fails, that is information, not failure.\*\* Return to Phase 2 with the new evidence. Never "fix" a failing verification by weakening the check.

\## Phase 6 - Report honestly

1\. \*\*Lead with the outcome:\*\* what the problem was, what the root cause was, what changed, and how it was verified.

2\. \*\*Report reality, not intention.\*\* If a test fails, say so and show the output. If a step was skipped or a case remains unverified, state it plainly. Never present hope as fact.

3\. \*\*Surface residual risks and follow-ups\*\* - known limitations, edge cases deliberately left out of scope, cleanup worth doing later - so the user can decide about them consciously.

\## Quick checklist

Before declaring any problem solved, all of these must be true:

\- \[ \] I can state the problem, the root cause (or requirements), and the constraints precisely.

\- \[ \] I read the actual code involved; I did not rely on assumptions.

\- \[ \] I considered more than one approach and chose deliberately.

\- \[ \] The change is the smallest one that fully solves the problem.

\- \[ \] I exercised the change end-to-end and observed correct behavior.

\- \[ \] I checked edge cases and the blast radius for regressions.

\- \[ \] My report matches what I actually observed, including anything that failed or was skipped.