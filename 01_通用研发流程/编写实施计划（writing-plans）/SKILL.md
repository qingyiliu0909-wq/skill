---
name: writing-plans
description: Use when you have a spec, requirements, or a mounted workflow for a multi-step task, before beginning execution
---

# Writing Plans

## Overview

Translate the available source material into an executable plan. Match the plan shape to the work: software implementation plans carry code, test, and commit detail; mounted business workflows carry business steps, required reading, evidence, and recovery guidance.

Assume the executor is capable but has no prior context about the project, workflow library, or supporting documents.

**Announce at start:** "I'm using the writing-plans skill to create the execution plan."

**Context:** If working in an isolated worktree, it should have been created via the `superpowers:using-git-worktrees` skill at execution time.

**Mounted task libraries:** If the workspace contains `superpowers.local.md`, read it before planning. When it declares an external task or workflow library relevant to the request, read the matching task script, standard-steps doc, or workflow mother-template first, then translate that business flow into the plan you write. Do not invent a parallel flow when the mounted task library already provides one.

**Save plans to:** `docs/superpowers/plans/YYYY-MM-DD-<feature-name>.md`
- (User preferences for plan location override this default)
- For a mounted business workflow, use the runtime plan path declared by its mother-template or workspace contract. When neither declares one, use the default above.

## Plan Type Selection

Choose one plan type before drafting:

1. **Mounted business workflow:** `superpowers.local.md` declares a task or workflow library, the request matches a registered workflow, and the primary deliverable is an analysis, report, export, operational result, or other business artifact. Use the Business Workflow Plan Format.
2. **Software implementation:** The primary deliverable is a codebase change. Use the Software Implementation Plan Format.
3. **Mixed work:** Separate business execution steps from software implementation tasks. Render each part with its matching format while preserving their dependency order.

The mounted workflow is the source of truth for business order and meaning. A standard step may be a concise natural-language description rather than a schema or machine contract. Read its linked documents and infer the execution detail needed by the runtime plan. Ask the human partner only when a material ambiguity cannot be resolved from the mounted assets.

## Business Workflow Plan Format

Compile the workflow mother-template and its referenced standard steps into the runtime plan. These fields describe the AI-generated plan, not a required authoring format for workflow contributors.

```markdown
# [Workflow Run Name] Plan

> **For agentic workers:** Execute with superpowers:executing-plans or superpowers:subagent-driven-development. Track progress with checkbox (`- [ ]`) syntax.

**Workflow Source:** [exact mother-template path]

**Goal:** [business outcome for this run]

**Available Inputs:** [confirmed inputs and unresolved input gaps]

**Expected Deliverables:** [physical artifacts or observable outcomes]

**Step Order:** [ordered list of expanded standard-step sources]

## Global Constraints

[Cross-step requirements derived from the workflow and essential supporting documents]

### Step N: [Business Step Name]

**Source:** [exact standard-step path]

**Read Before Doing:**
- [documents or skills to load immediately before this step]

**Inputs:**
- [artifacts or decisions consumed by this step]

**Actions:**
- [ ] [concrete action]

**Produces:**
- [artifacts or observable results]

**Proof of Done:**
- [ ] [physical, inspectable evidence that must exist before advancing]

**Recovery:**
- [failure or quality-gap signal] → [knowledge or case-library path to search, then retry or return to the named step]
```

Preserve the mother-template's order. Expand every referenced standard step exactly once unless the workflow explicitly makes it conditional. Keep linked knowledge unloaded until the plan or current step says it is needed. Include `Files`, `Interfaces`, `Tech Stack`, TDD steps, test code, and commits only inside a step whose observable work is software implementation.

### Business Workflow Self-Review

Before saving the plan, verify:

1. **Source coverage:** Every selected mother-template step appears once and points back to its source.
2. **Progressive disclosure:** Each document or Skill is scheduled at the latest safe point, normally `Read Before Doing` or `Recovery`.
3. **Evidence:** Every step has inspectable Proof of Done appropriate to its outcome.
4. **Recovery:** Failures and quality gaps name searchable knowledge or a clear return step.
5. **Author intent:** Natural-language workflow and standard-step meaning is preserved; inferred detail does not invent a different business flow.

## Software Implementation Plan Format

Use the remaining sections for software implementation. Write comprehensive implementation plans with exact files, interfaces, code, tests, TDD, and frequent commits.

## Scope Check

If the spec covers multiple independent subsystems, it should have been broken into sub-project specs during brainstorming. If it wasn't, suggest breaking this into separate plans — one per subsystem. Each plan should produce working, testable software on its own.

## File Structure

Before defining tasks, map out which files will be created or modified and what each one is responsible for. This is where decomposition decisions get locked in.

- Design units with clear boundaries and well-defined interfaces. Each file should have one clear responsibility.
- You reason best about code you can hold in context at once, and your edits are more reliable when files are focused. Prefer smaller, focused files over large ones that do too much.
- Files that change together should live together. Split by responsibility, not by technical layer.
- In existing codebases, follow established patterns. If the codebase uses large files, don't unilaterally restructure - but if a file you're modifying has grown unwieldy, including a split in the plan is reasonable.

This structure informs the task decomposition. Each task should produce self-contained changes that make sense independently.

## Task Right-Sizing

A task is the smallest unit that carries its own test cycle and is worth a
fresh reviewer's gate. When drawing task boundaries: fold setup,
configuration, scaffolding, and documentation steps into the task whose
deliverable needs them; split only where a reviewer could meaningfully
reject one task while approving its neighbor. Each task ends with an
independently testable deliverable.

## Bite-Sized Task Granularity

**Each step is one action (2-5 minutes):**
- "Write the failing test" - step
- "Run it to make sure it fails" - step
- "Implement the minimal code to make the test pass" - step
- "Run the tests and make sure they pass" - step
- "Commit" - step

## Plan Document Header

**Every plan MUST start with this header:**

```markdown
# [Feature Name] Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** [One sentence describing what this builds]

**Architecture:** [2-3 sentences about approach]

**Tech Stack:** [Key technologies/libraries]

## Global Constraints

[The spec's project-wide requirements — version floors, dependency limits,
naming and copy rules, platform requirements — one line each, with exact
values copied verbatim from the spec. Every task's requirements implicitly
include this section.]

---
```

## Task Structure

````markdown
### Task N: [Component Name]

**Files:**
- Create: `exact/path/to/file.py`
- Modify: `exact/path/to/existing.py:123-145`
- Test: `tests/exact/path/to/test.py`

**Interfaces:**
- Consumes: [what this task uses from earlier tasks — exact signatures]
- Produces: [what later tasks rely on — exact function names, parameter
  and return types. A task's implementer sees only their own task; this
  block is how they learn the names and types neighboring tasks use.]

- [ ] **Step 1: Write the failing test**

```python
def test_specific_behavior():
    result = function(input)
    assert result == expected
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/path/test.py::test_name -v`
Expected: FAIL with "function not defined"

- [ ] **Step 3: Write minimal implementation**

```python
def function(input):
    return expected
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/path/test.py::test_name -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/path/test.py src/path/file.py
git commit -m "feat: add specific feature"
```
````

## No Placeholders

Every step must contain the actual content an engineer needs. These are **plan failures** — never write them:
- "TBD", "TODO", "implement later", "fill in details"
- "Add appropriate error handling" / "add validation" / "handle edge cases"
- "Write tests for the above" (without actual test code)
- "Similar to Task N" (repeat the code — the engineer may be reading tasks out of order)
- Steps that describe what to do without showing how (code blocks required for code steps)
- References to types, functions, or methods not defined in any task

## Remember
- Exact file paths always
- Complete code in every step — if a step changes code, show the code
- Exact commands with expected output
- DRY, YAGNI, TDD, frequent commits

## Self-Review

After writing the complete plan, look at the spec with fresh eyes and check the plan against it. This is a checklist you run yourself — not a subagent dispatch.

**1. Spec coverage:** Skim each section/requirement in the spec. Can you point to a task that implements it? List any gaps.

**2. Placeholder scan:** Search your plan for red flags — any of the patterns from the "No Placeholders" section above. Fix them.

**3. Type consistency:** Do the types, method signatures, and property names you used in later tasks match what you defined in earlier tasks? A function called `clearLayers()` in Task 3 but `clearFullLayers()` in Task 7 is a bug.

If you find issues, fix them inline. No need to re-review — just fix and move on. If you find a spec requirement with no task, add the task.

## Execution Handoff

After saving the plan, offer execution choice:

**"Plan complete and saved to `docs/superpowers/plans/<filename>.md`. Two execution options:**

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?"**

**If Subagent-Driven chosen:**
- **REQUIRED SUB-SKILL:** Use superpowers:subagent-driven-development
- Fresh subagent per task + two-stage review

**If Inline Execution chosen:**
- **REQUIRED SUB-SKILL:** Use superpowers:executing-plans
- Batch execution with checkpoints for review
