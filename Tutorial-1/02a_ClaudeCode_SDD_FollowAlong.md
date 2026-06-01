# Claude Code for Spec-Driven Development
## Follow-Along Guide — MNIST Fully-Connected Classifier

> **Session:** Graduate Course: Generative AI · 90-Minute Session  
> **Lab:** QUEST Lab · Dept. of Computational & Data Sciences · IISc Bangalore  
> **Running example:** A fully-connected MNIST classifier in PyTorch, built entirely spec-first across 4 exercises.

---

## Slide-to-Exercise Map

---

## Exercise 1 — Install, Init, and Explore

---

### Step 1 — Install Claude Code

https://code.claude.com/docs/en/quickstart -- Follow instructions for your OS

For MacOS/Linux/WSL: Execute the following curl.
curl -fsSL https://claude.ai/install.sh | bash

---

### Step 2 — Set up the project folder

```bash
mkdir mnist-sdd && cd mnist-sdd
git init
```

---

### Step 3 — Launch Claude Code and initialise the project

```bash
claude
```

Then inside the session:

Prompt claude with your overall goal for this project. And ask it to create the CLAUDE.md memory file. It is created for the first time with the /init command.

Example of a starting prompt:

<prompt>
We want to create a simple dense neural netwrok that accepts grayscale images as input and classifies them into one of the 10 numerals 0-9. The task is called as the MNIST handwritten digit recognition task. For this, we will perform a spec driven development process. First create an appropriate CLAUDE.md file and then create a skeleton of the SPEC.md file. We will use Python with PyTorch. We need to create data loading pipeline, training-validation pipeline, inference pipeline and hyperparameter tuning pipeline. All activities must be controlled from a config file.
</prompt>


Claude will follow your prompt repo and generate a `CLAUDE.md` and `SPEC.md` files. Accept the output or make edits as you deem appropriate.

Usually SPEC.md will contain some open questions that claude wants us to answer. You can directly edit the file in vscode (uses 0 tokens) or prompt claude to update (will use tokens)

---

### Step 4 — Observe what was generated

Open CLAUDE.md and SPEC.md

Now to proceed further, ask claude to create a PLAN.md to implement the SPEC.md step-by-step. Verify and execute. (GO TO EXERCISE 3)

At the end, ask claude to create a README.md with a tutorial style explanation of how to use the code.

---

## Exercise 2 — Create the git-commit Skill

---

### Step 1 — Paste the skill-creation prompt

Inside the active Claude Code session:

```
Create a project-scoped skill called git-commit for this MNIST repo.
It should run git status and git diff HEAD as dynamic context,
generate a commit message referencing what changed in the model or
training loop, then commit. Restrict it to git bash tools only.
Never push automatically.
```

Claude will create the directory and write the `SKILL.md` file.

---

### Step 2 — Inspect what Claude created

```bash
cat .claude/skills/git-commit/SKILL.md
```

Verify the file contains:

- YAML frontmatter with `name`, `description`, and `allowed-tools`
- Dynamic context lines using `!` shell injection (`git status`, `git diff HEAD`)
- Step-by-step instructions with a confirmation step before committing
- No `git push` anywhere in the instructions

The file should look similar to this (not exact, but similar):

```yaml
---
name: git-commit
description: >
  Stage all changes and create a conventional git commit.
  Auto-invoke when user says "commit", "save progress",
  or "checkpoint my work". Do NOT push automatically.
allowed-tools: Bash(git add:*), Bash(git status:*),
               Bash(git diff:*), Bash(git commit:*)
---
## Dynamic Context
- Status: !`git status`
- Diff:   !`git diff HEAD`
- Branch: !`git branch --show-current`
- Recent: !`git log --oneline -5`

## Instructions
1. Summarize what changed (model architecture, training loop, data loading, tests)
2. Propose a commit message: `<type>(<scope>): <summary>` — show it to the user
3. Wait for confirmation, then run `git add -A && git commit -m "<message>"`
4. Report the commit hash. Do NOT run git push.
```

---

### Step 3 — Confirm the skill is loaded

```
/skills
```

`/git-commit` should now appear in the list alongside the built-in bundled skills.

If not loaded, exit and launch claude again with claude --resume and select the session

---

### Step 4 — Test

```
/git-commit
```

---

## Exercise 3 — Write the MNIST Spec
 
**Important: write this before Claude writes any code.**

In the Exercise 1, we did a shortcut as MNIST is a standard project. This exercise is for a new problem that claude has not seen in its training data.
---

### Step 1 — Create `SPEC.md` from memory

```bash
touch SPEC.md
```

Open in any editor and write your own version first — without looking at the slide. Use these five headings as prompts:

```
Goal:
Architecture:
Constraints:
Data:
Training:
Acceptance Criteria:
Output Files:
```

---

### Step 2 — Peer review

Swap your spec with a partner. Check each other's spec for:

- Is the goal unambiguous?
- Are acceptance criteria verifiable (pass/fail)?
- Are output files listed explicitly?
- Are there implicit assumptions that should be stated?

---

### Step 3 — Finalize `SPEC.md`

Replace the contents of your `SPEC.md` with the finalized version:

```markdown
Goal
  Fully-connected neural network for MNIST digit classification in PyTorch.

Architecture
  Input(784) → Linear(256, ReLU) → Linear(128, ReLU) → Output(10)

Constraints
  - PyTorch only; no conv layers; no external model libraries (e.g. timm)
  - Python 3.11, type hints required, no raw loops over batches

Data
  torchvision MNIST · normalize: mean=0.1307, std=0.3081
  batch_size=64

Training
  Loss:      CrossEntropyLoss
  Optimizer: Adam, lr=1e-3
  Epochs:    5

Acceptance Criteria
  - Test accuracy > 97% by epoch 5
  - Training loss printed every 100 batches
  - pytest tests/test_model.py passes (input/output shapes, forward pass)

Output Files
  model.py   train.py   evaluate.py   tests/test_model.py
```

---

### Step 4 — Make the first real commit using the skill

```
/git-commit
```

Claude reads the diff (new `SPEC.md`), and proposes a message such as:

```
docs: add MNIST FC classifier spec
```

Confirm → your first commit lands. Check with `git log --oneline`.

---

## Exercise 4 — Full SDD Workflow: Plan → Implement → Verify → Commit
**Slides 18–21 · ~20 min**  
*The main follow-along. Complete phases 2–4 while the instructor narrates each phase.*

---

### Phase 2 — Plan 

#### Step 1 — Ask Claude to plan before writing any code

```
Read the spec in SPEC.md.
Before writing any code, output a step-by-step implementation plan, into PLAN.md
Identify risks and ambiguities. Do not start coding until I approve the plan. think hard
```

The `think hard` suffix triggers extended reasoning — Claude will reason through the plan before presenting it.

#### Step 2 — Review the plan 

Discuss: does Claude's plan match the spec exactly? Did it surface any ambiguity? For example:
- Does `batch_size=64` apply to validation and test sets too, or only training?
- What happens if the MNIST download fails?

#### Step 3 — Approve the plan

```
The plan looks good. Proceed with Phase 1 only: implement model.py.
Do not start train.py yet.
```

> **Rule:** if the plan reveals a spec ambiguity, fix `SPEC.md` first, then re-ask for the plan. Never start implementing from an ambiguous spec.

---

### Phase 3 — Implement 

Work through four files, one at a time. Review the diff and commit after each.

---

#### File 1 — `model.py`

**Prompt:**

```
Implement Phase 1 of the plan: model.py with the architecture from the spec.
Do not move to train.py yet.
```

**Review:**

```
/diff
```

Check for: correct layer sizes (784 → 256 → 128 → 10), ReLU activations present, type hints on all functions, no raw Python loops over batch elements.

**Commit:**

```
/git-commit model-architecture
```

Claude proposes e.g. `feat(model): add FC MNIST classifier (784→256→128→10)`. Confirm.

---

#### File 2 — `train.py`

**Prompt:**

```
Now implement train.py following Phase 2 of the plan.
Use the spec: CrossEntropyLoss, Adam lr=1e-3, 5 epochs, batch_size=64.
Print loss every 100 batches.
```

**Review:** `/diff` — confirm loss function, optimizer, print frequency match the spec exactly.

**Commit:**

```
/git-commit training-loop
```

---

#### File 3 — `evaluate.py`

**Prompt:**

```
Implement evaluate.py: load the trained model, run on the MNIST test set,
report per-epoch accuracy. Must satisfy: accuracy > 97% by epoch 5.
```

**Review:** `/diff` — confirm it loads from a saved checkpoint, not from the training script directly.

**Commit:**

```
/git-commit evaluation
```

---

#### File 4 — `tests/test_model.py`

**Prompt:**

```
Implement tests/test_model.py with pytest.
Test: correct input/output shapes (batch x 784 in, batch x 10 out).
Test: forward pass does not raise.
Test: output is a valid probability distribution after softmax.
```

**Review:** `/diff` — confirm three distinct test functions, no training data loaded in tests.

**Commit:**

```
/git-commit model-tests
```

---

### Phase 4 — Verify 

#### Step 1 — Run the tests

```
Run the tests in tests/test_model.py.
If any fail, fix them without changing the spec or acceptance criteria.
```

#### Step 2 — Use /loop if tests fail

```
/loop
```

Claude runs the test, fixes any failures, re-runs — iterates until all tests are green.

#### Step 3 — Commit the verified state

```
/git-commit verify-all-tests-pass
```

#### Step 4 — Check context usage

```
/context
```

If usage is above 80%, compact before continuing:

```
/compact focus on model.py, train.py, and test results
```

---

### Phase 5 — Iterate 

If something is wrong — a test is failing or behaviour doesn't match the spec — the correct fix is always to update the spec first, then re-implement. Never patch the code to work around spec ambiguity.

**❌ Wrong:**

Editing `model.py` directly to make a test pass, without touching `SPEC.md`.

**✅ Right:**

```
The acceptance criterion of 97% accuracy assumes proper data normalization.
Update SPEC.md to clarify that normalization applies to both train and test sets,
then re-run the relevant parts of the plan.
```

Then commit the spec change:

```
/git-commit spec-normalize-clarification
```

---

## Git Log at the End of the Session

After completing all four exercises, your commit history should look like this:

```
feat(tests): add pytest model tests
feat(eval): add evaluation script
feat(train): add training loop
feat(model): add FC MNIST classifier (784→256→128→10)
docs: add MNIST FC classifier spec
```

This history is itself a record of the SDD workflow — spec first, then each component in order, each verified before the next begins.

---

## Quick Reference: Commands Used in This Session

| Command / Syntax | Purpose |
|------------------|---------|
| `claude` | Launch interactive REPL |
| `/init` | Generate CLAUDE.md for the repo |
| `/memory` | Open CLAUDE.md for editing |
| `# text` | Quick-write a line to CLAUDE.md |
| `/model` | Switch model mid-session |
| `/skills` | List all loaded skills |
| `/diff` | Review all changes Claude made this session |
| `/context` | Check context window usage |
| `/compact focus on X` | Compress history, keep X in focus |
| `/loop` | Iterative fix-and-retest cycle |
| `/git-commit <scope>` | Stage, propose message, and commit (custom skill) |
| `think hard` | Trigger extended reasoning on a prompt |
| `@src/model.py` | Reference a specific file in a prompt |
| `!git status` | Run a shell command inline in a prompt |

---

## Homework

Extend the `git-commit` skill into a full git workflow skill:

1. **Branching** — create a feature branch from `main` before implementing
2. **PR description** — summarize all commits since branching into a pull request description
3. **Pre-commit check** — run `pytest` and abort the commit if any test fails
4. Scope all tools correctly with `allowed-tools`

**Submit:** the `SKILL.md` file + a 1-page spec for the skill itself (written before you build it).

---

*QUEST Lab · CDS · IISc Bangalore*
