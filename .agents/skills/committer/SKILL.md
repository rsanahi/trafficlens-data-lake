---
name: committer
description: Commit changes to git repository in a structured way
---

# Committer Skill

This skill provides a standard for creating git commits within the TrafficLens project. All changes must be committed using the **Conventional Commits** specification to ensure a clean and readable history.

## Commit Message Format

Each commit message consists of a **header**, a **body**, and a **footer**.

```text
<type>(<scope>): <description>

[optional body]

[optional footer(s)]
```

### 1. Header (Required)
The header has a special format that includes a `type`, a `scope`, and a `description`.

*   **Type**: Must be one of the following:
    *   `feat`: A new feature
    *   `fix`: A bug fix
    *   `docs`: Documentation only changes
    *   `style`: Changes that do not affect the meaning of the code (white-space, formatting, missing semi-colons, etc)
    *   `refactor`: A code change that neither fixes a bug nor adds a feature
    *   `perf`: A code change that improves performance
    *   `test`: Adding missing tests or correcting existing tests
    *   `chore`: Changes to the build process or auxiliary tools and libraries such as documentation generation

*   **Scope**: A phrase describing the section of the codebase affected (e.g., `core`, `frontend`, `dbt`, `ocr`).
*   **Description**: A short summary of the code changes.
    *   Use the imperative, present tense: "change" not "changed" nor "changes".
    *   Don't capitalize the first letter.
    *   No dot (.) at the end.

### 2. Body (Optional)
*   Just as in the **description**, use the imperative, present tense: "change" not "changed" nor "changes".
*   The body should include the motivation for the change and contrast this with previous behavior.

### 3. Footer (Optional)
*   The footer should contain any information about **Breaking Changes** and is also the place to reference GitHub issues that this commit closes.
*   **Breaking Changes** should start with the word `BREAKING CHANGE:` with a space or two newlines. The rest of the commit message is then used for this.

## Examples

**Feature**
```text
feat(frontend): add interactive map filters

Added a sidebar filter to allow users to select specific dates and trips.
Updated the PyDeck visualization to respect these filters.
```

**Bug Fix**
```text
fix(core): correct source_file mismatch in silver layer

The source_file column included the full absolute path, causing joins with Gold layer to fail.
Changed logic to extract only the filename.
```

**Documentation**
```text
docs(readme): update data lake architecture diagram
```