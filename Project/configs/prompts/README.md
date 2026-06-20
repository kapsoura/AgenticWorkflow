# Prompt Configs

This folder stores prompt and system-message templates used by the workflow agents.

Files:
- `extraction_system.md` - system prompt for complaint extraction
- `extraction_user.md` - user prompt for complaint extraction
- `extraction_reflection.md` - reflection prompt for extraction review
- `subqueries_system.md` - system prompt for subquery generation
- `subqueries_user.md` - user prompt for subquery generation
- `questions_system.md` - system prompt for report questions
- `questions_user.md` - user prompt for report questions

Templates use `$placeholders` and are rendered by `src.utils.prompt_store`.