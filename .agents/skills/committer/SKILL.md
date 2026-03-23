---
name: committer
description: Commit changes to git repository in a structured way
---

# Committer Skill

## ⚡ How to Use This Skill

When asked to commit changes, **ALWAYS** use the `smart_commit.py` script instead of raw `git commit` commands. This enforces all commit rules automatically.

### Command

```bash
python .agents/skills/committer/scripts/smart_commit.py \
  <type> <scope> "<description (max 50 chars)>" \
  [--body "Extended body text"] \
  file1.py file2.sql ...
```

### Example Usage

```bash
# Commit a new feature
python .agents/skills/committer/scripts/smart_commit.py \
  feat frontend "add trip filter to interactive map" \
  --body "Added multiselect sidebar filter. Only trips with GPS data are shown." \
  frontend/pages/1_Interactive_Map.py

# Commit a bug fix
python .agents/skills/committer/scripts/smart_commit.py \
  fix dbt "normalize source_file to filename only" \
  core/dbt_project/models/silver/stg_telemetry.sql
```

> **IMPORTANT**: The script will **reject** descriptions longer than 50 characters with an error. Fix the description before retrying.

---

## Commit Message Format Reference

```text
<type>(<scope>): <description>   ← max 50 chars

[optional body - explain WHY, not WHAT]

[optional footer - BREAKING CHANGE: or Closes #issue]
```

### Commit Types

| Type       | When to use |
|------------|-------------|
| `feat`     | New feature |
| `fix`      | Bug fix |
| `docs`     | Documentation only |
| `style`    | Formatting, no logic change |
| `refactor` | Code change that is neither fix nor feature |
| `perf`     | Performance improvement |
| `test`     | Adding/fixing tests |
| `chore`    | Build process, tooling |
| `build`    | Build system changes |
| `ci`       | CI/CD changes |

### Description Rules

- **Max 50 characters**
- Imperative tense: `"add"`, not `"added"` or `"adds"`
- No capital first letter
- No period at the end

### Scope Reference (TrafficLens)

| Scope      | Files |
|------------|-------|
| `core`     | `core/*.py` |
| `ocr`      | `core/viofo_ocr.py` |
| `ingest`   | `core/batch_ingest.py` |
| `dbt`      | `core/dbt_project/` |
| `frontend` | `frontend/` |
| `gold`     | `core/dbt_project/models/gold/` |
| `silver`   | `core/dbt_project/models/silver/` |
| `repo`     | `.gitignore`, `README.md` |
| `skills`   | `.agents/` |