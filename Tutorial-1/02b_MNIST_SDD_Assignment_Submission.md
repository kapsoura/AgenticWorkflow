# Assignment: Full MNIST Pipeline Using SDD

## Objective
Build a complete MNIST classification project using Spec-Driven Development (SDD), including:
- model build
- training
- validation
- testing

Use one continuous Claude Code session (or any equivalent agentic development environment session).

## Session Constraint
- Use only one session for the full assignment lifecycle.
- You may continue that same session across multiple sittings.
- Ensure all conversation logs remain under that same session.

## Required Deliverables
Your submission folder must include all of the following:

1. `CLAUDE.md`
   - Or equivalent memory/context file used by your agentic workflow.

2. `SPEC.md`
   - The specification contract for the MNIST system.

3. `<username>.md`
   - Contents exported from the session (`/export`) in markdown form.

4. `results.md`
   - Must contain train, validation, and test metrics.
   - Metrics should match what you define in `SPEC.md`.

5. Optional: one PNG image
   - Suggested contents:
     - training/validation/testing curves
     - visualization of 10-class classification metrics (any clear format)

## Packaging Instructions
1. Create one folder named `<username>`.
2. Place all required files (and optional PNG, if provided) inside that folder.
3. Compress the folder as `<username>.zip`.
4. Submit/attach the zip file.

## Recommended Folder Layout
```text
<username>/
  CLAUDE.md
  SPEC.md
  <username>.md
  results.md
  metrics_plot.png            # optional
```

## Validation Checklist Before Submission
- [ ] Full MNIST model implemented.
- [ ] Training pipeline completed.
- [ ] Validation pipeline completed.
- [ ] Testing pipeline completed.
- [ ] Single continuous session used and logged.
- [ ] `CLAUDE.md` (or equivalent) included.
- [ ] `SPEC.md` included.
- [ ] `<username>.md` from `/export` included.
- [ ] `results.md` includes train/val/test metrics aligned with `SPEC.md`.
- [ ] Optional PNG included (if created).
- [ ] Final archive named `<username>.zip`.
