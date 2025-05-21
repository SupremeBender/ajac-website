# GitHub Copilot Instructions

# AJAC DCS Mission Planner – Copilot Operational Guidelines

This project is a **Flask app with an HTML frontend** for our **DCS (Digital Combat Simulator) mission planning website**. It is hosted using **Apache** and **systemd**, deployed on a VPS under the fictional command **AJAC (Arctic Joint Air Command)**, operating out of **Andøya Airbase**.

---

## PRIME DIRECTIVES

* **DO NOT** make broad or multi-file changes without explicit permission.
* If uncertain about an instruction, **ask questions until you're sure**.
* **NEVER touch anything inside the `/reference` folder** without being explicitly told to.
* Use **clear, instructional comments** and **print/debug logs** where helpful.
* The user is still learning to code — explain what you are doing in clear terms.
* Avoid deleting or refactoring large chunks of code unless you are 100% sure of the implications and have been explicitly cleared to do so.
* Keep the codebase **clean** and **readable**, but avoid unnecessary abstraction.

---

## BRANCH POLICY

* All development occurs in the **`beta` branch**.
* **NEVER push or base changes on `main`** unless explicitly told to do so.

---

## FILE STRUCTURE

```
project-root/
├── app/                   # Flask app package
│   ├── __init__.py        # App factory
│   ├── models/            # DB models
│   ├── utils/             # Shared logic
│   └── features/          # Modular blueprints
│       ├── auth/
│       ├── admin/
│       ├── signup/
│       └── ...
├── config/               # Static JSON config files
├── data/                 # Persistent campaign/mission data (was: instance/)
├── static/               # Global static assets (JS, CSS, images)
├── templates/            # Global Jinja templates
├── tests/                # Test cases (unit/integration)
├── logs/                 # Log files
├── docs/                 # Markdown documentation and structure.txt
├── start_all.sh          # Systemd/Apache startup script
├── wsgi.py               # Apache WSGI entry point
├── disc_bot.py           # Discord integration script (if used)
├── config.py             # App config
├── requirements.txt
├── README.md
└── LICENSE
```

---

## CODE EDITING RULES

### ✅ GENERAL PRINCIPLES

* Use **Python 3.10+** and follow **PEP8** for style.
* Use **Flask Blueprints** for modular design.
* Avoid circular imports — follow an **app factory pattern**.
* Always validate request data (e.g. `pydantic`, `marshmallow`, or manual checks).
* Log errors using the `logging` module, not `print()`.
* Use try-except where failure is possible. Always fail gracefully.
* Do **not** use `eval()` or `exec()` unless explicitly permitted.

### 📐 STRUCTURE AND CLEANLINESS

* Remove unused imports or variables, but only if clearly obsolete.
* Never leave commented-out blocks unless actively debugging.
* Clearly label any debug or test-only code.

### 📄 JINJA/HTML

* Use semantic HTML5 elements.
* Ensure all forms have labels and proper ARIA roles.
* Use `alt` text and `aria-label` for all media/images.
* Maintain WCAG 2.1 AA accessibility minimum, AAA where feasible.

### 🎨 CSS

* Use CSS Grid/Flexbox, and support dark mode with `prefers-color-scheme`.
* Use logical properties (`margin-block`, `padding-inline`) where practical.
* Avoid pixel-based layouts in favor of `rem`, `vh`, `vw`.

### 🧠 JAVASCRIPT

* Use **ES2020+** features.
* Prefer `const`/`let`, avoid `var`.
* Use async/await rather than callbacks.
* Handle promise rejections with `.catch()` or try/catch.
* Don’t use jQuery.
* Avoid unnecessary dependencies or libraries.

---

## COPILOT LARGE EDIT PROTOCOL

### 🔍 MANDATORY PLANNING

For edits in files >300 lines or when doing multiple dependent changes:

**Submit a clear plan in this format:**

```markdown
## PROPOSED EDIT PLAN
Working with: [filename]
Total planned edits: [number]

1. [Edit 1] – Purpose: [why]
2. [Edit 2] – Purpose: [why]
...
Do you approve this plan? I’ll begin with edit 1 upon confirmation.
```

### 🛠 EDIT EXECUTION RULES

* Apply one logical change at a time.
* After each change, confirm with:

  * "Completed edit \[#] of \[total]. Ready for next edit?"
* If an unexpected issue appears, **stop and revise the plan**.
* If changes are too large, suggest splitting over multiple sessions.
* After making a change, let the user know if soemthing needs a restart before testing (for example apache, or browser refresh)

### 🔁 REFACTORING

* Break into safe, intermediate steps.
* Use temporary duplication if needed to preserve stability.
* Ensure all intermediate states are functional.

---

## TESTING & VALIDATION

* If a change breaks anything, revert it immediately.
* Explain why something broke and how to fix it.
* Use debug comments/logs to trace logic if needed.
* Prefer manual tests unless a test framework is introduced.

---

## SECURITY

* Sanitize all user inputs (especially from forms).
* Never trust JSON or query params without checks.
* Use parameterized queries where relevant.
* Apply `HttpOnly`, `Secure`, and `SameSite` flags to cookies.
* Include CSP headers via Apache or Flask where applicable.

---

## FINAL NOTE

* This is a **live tool** used by real players. Be accurate.
* Don’t guess or assume.
* Always prioritize **clarity**, **functionality**, and **maintainability**.

---
