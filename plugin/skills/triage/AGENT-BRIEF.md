# Writing a work-ready brief

A brief records the verified contract for an issue or the remaining work on a
pull request. Draft it in the consumer's language and template. Post it only
after explicit approval.

## Principles

### Durable, but concrete

Describe behavior contracts, interfaces and config shapes that remain useful
when files move. Include a concrete type or command only when repository
evidence establishes it. Avoid line numbers and speculative paths.

### Behavior, not an implementation walkthrough

State current behavior, desired behavior and constraints. Leave implementation
choices open unless the repository or a recorded decision already constrains
them.

### Independently verifiable completion

Every acceptance criterion must name an observable result and, where known, its
verification method. Discover the repository's test, build, security,
configuration and operational gates; do not insert a familiar command or
platform requirement by default.

### Explicit scope

Record adjacent work that is deliberately excluded. Include relevant risk,
rollback and compatibility constraints without copying an umbrella plan.

## Fallback template

Use a consumer-owned template when one exists. Otherwise adapt:

```markdown
## Work-ready brief

**Category:** <verified repository category>
**Summary:** <one-line outcome>

### Current behavior and evidence
<what happens now, how it was verified, and remaining uncertainty>

### Desired behavior
<observable result, edge cases and failure contract>

### Relevant contracts
- <interface, data shape or configuration contract>

### Acceptance criteria
- [ ] <observable result and verification>
- [ ] <repository-required quality or operational gate>

### Out of scope
- <explicit boundary>
```

For a pull request, current behavior describes the existing diff and desired
behavior describes what remains before it is ready.

## Example

```markdown
## Work-ready brief

**Category:** <repository's verified defect category>
**Summary:** Prevent duplicate processing when the same command is retried

### Current behavior and evidence
The deterministic reproduction submits the same command identifier twice. Both
submissions create an effect.

### Desired behavior
The second submission is idempotent. It creates no additional effect and
returns the repository's documented duplicate-result contract.

### Relevant contracts
- Command identifier — defines idempotency across retries
- Persistence boundary — must make the check and effect atomic

### Acceptance criteria
- [ ] Replaying one identifier creates exactly one effect
- [ ] Different identifiers continue to be processed independently
- [ ] The repository's required checks pass with a regression test

### Out of scope
- Changing the producer's retry policy
```

## Reject weak briefs

A brief is not ready when it contains only «fix the bug», points to a line
number without a behavior contract, invents a technology-specific gate, or has
no independently verifiable acceptance criteria.
