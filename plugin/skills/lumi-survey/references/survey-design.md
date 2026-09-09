# Design a Lumi survey

Use the consumer's product goal and the resolved package API. The labels below
describe survey purposes, not guaranteed export or preset names.

## Select one learning objective

| Purpose | Useful question shape | Watch for |
|---|---|---|
| Overall experience | short rating plus optional reason | a score alone rarely explains what to change |
| Specific feature feedback | binary or small scale plus context | avoid generalizing beyond that feature |
| Discovery | task or goal, completion, and obstacle | keep free text bounded and privacy-safe |
| Task success | intended task, completion, and blocker | use task options based on research, not invention |
| Priority research | randomized multi-select or ranking | requires a real candidate set and analysis plan |
| Custom branching | typed questions with conditional follow-up | verify every branch against installed types |

Prefer the shortest survey that can answer the stated question. Use neutral,
concrete language, make optional questions visibly optional, and explain why
feedback is collected and how it is used when the surrounding service does not
already do so.

## Discover the supported API

Inspect the resolved package exports, declarations, documentation, examples,
and tests. Confirm:

- available widget components and configuration types;
- question, option, validation, branching, and preset support;
- required style imports and peer dependencies;
- event callbacks and error behavior;
- storage, dismissal, consent, and server-rendering behavior.

Do not import from internal build paths. If documentation and exported types
disagree, stop and resolve the package-version contract before implementation.

## Minimize data

- Avoid asking for identity, case details, diagnoses, contact information, or
  other personal data unless the approved purpose explicitly requires it.
- Treat free text as capable of containing sensitive data even when the prompt
  asks users not to enter it. Minimize length, recipients, access, retention,
  and logging accordingly.
- Keep context tags low-cardinality and necessary for the learning question.
  Never place national identity numbers, names, emails, case IDs, request IDs,
  tokens, or sensitive attributes in tags.
- Determine analytics events from the accepted measurement plan. Do not attach
  raw answers or feedback text to general analytics.

## Storage and consent

Use the package's supported storage strategy together with the consumer's
actual consent architecture and privacy policy. Do not infer a strategy from
whether an app is public or internal. Store only the minimum UI state needed to
display, dismiss, or suppress the survey, and never store credentials or raw
feedback in browser storage.

## Accessibility and failure states

Verify focus order, accessible names, error association, keyboard operation,
screen-reader announcements, contrast, dismissal, and return of focus. Ensure
the page remains usable when package JavaScript, styles, storage, or submission
fails. A submission error must not trap the user or imply that feedback was
received.
