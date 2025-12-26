# CLAUDE.md

## 1. Claude Personality & Behavior

Claude should always:

- Be **precise**, **senior-engineer level**, and **explicit**.
- Avoid filler or conversational fluff.
- Prefer **clean, composable, minimal** code.
- Use the tech stack in this repo as the source of truth.
- When unsure, propose **two options with tradeoffs**.
- Output **only what is asked**.
- Escape code blocks properly.
- Avoid generaing summary md files unless needed for future context

---

## 2. Architectural Prompts

```text
You are designing a production-grade architecture for this repository.
- Use Mermaid for diagrams.
- Use explicit components, queues, APIs, storage, events.
- Adhere to Design patterns (e.g. gang of 4)
- Label all protocols and responsibilities.
- Integrate with existing components in this repo.
- Output only the diagram and a short explanation section.
- Do not over engineer!
```

To update architecture:

```text
Modify the architecture to incorporate the following new requirements:
<INSERT REQUIREMENTS>

Ensure the updated diagram remains coherent and aligned with existing names in this repo.
```

---

## 3. Code Generation Prompts

General pattern:

```text
Write code that integrates with this repository.

Constraints:
- Match existing folder structure.
- Use the same naming conventions.
- Do not invent abstractions unless required.
- Keep functions small and testable.
- Include a test file when appropriate.
- Prefer golang for most everything backend
- Prefer React for everything front end
- Prefer python for AI Based or Infrastreucture Dev Based
- Always try to use the latest possible version of packages with the exception of alpha and beta (unless no other option)
- Do not hard code things in the code where they can be configurable or bootstrapped
```

Refactor:

```text
Refactor the following code without changing behavior.
Keep logic identical. Only improve structure and readability.

<PASTE CODE>
```

Bug fix:

```text
Identify the bug in this snippet. Fix it. Explain the fix in 2 sentences.

<PASTE CODE>
```

---

## 4. UI / Frontend Prompts

```text
Generate a React component using:
- React + Typescript + Mantine
- No inline styles
- Maintain the existing design system


Component requirements:
- Make small components, seperate shared components into a shared folder
- keep related view components in the view folder
- NEVER hard code logic in the UI that can be derived via the backend - in fact suggest if we should move logic to the backend api (go)
if you think that is better
```

UI concept:

```text
Design a UI concept in structured text.
Do NOT generate images.
Describe layout, states, interactions.
Respect Tailwind + component patterns in this repo.
```

---

## 5. Container / Infra / Deploy Prompts

```text
Generate a deployment spec using the patterns in this repo.
- Do not change env var names.
- Use deterministic ports.
- Assume production sensibility.
- Use docker compose (not docker-compose)
- Usedocker-compose.dev.yml file for all workflows not related to ci
```

---

## 6. Tests

Backend:

```text
Generate table-driven tests for this function.
Include edge cases.

<PASTE CODE>
```

Frontend:

```text
Generate Playwright tests for this React component.
Use stable, semantic selectors.

<PASTE CODE>
```

---

## 7. Repo-Aware Prompting

```text
Read the repository structure and confirm conventions:
- Folder names
- File layout
- Naming patterns
- Existing types, interfaces, models

Then apply those conventions to the output.
```

---

## 8. Escape Rules

Claude should always:

- Escape backticks inside fenced blocks.
- Avoid YAML indentation errors.
- For nested prompts, use quadruple-backtick fences like this file.

If generating a prompt for another AI:

````md
```prompt
<CONTENTS>
```
