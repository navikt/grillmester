---
name: grillmester-integration-tests
description: "Designs narrow integration tests that exercise a real adapter or boundary through its public interface without booting the whole application. Use for repository, database, HTTP-client, message-adapter, filesystem, or similar contract tests; use grillmester-e2e-tests when the assembled app must boot."
---

# Integration Tests

Exercise the smallest real boundary that can prove the contract. Discover the
repository's stack and test conventions before choosing frameworks, fixtures,
or commands.

## 1. Discover the test contract

Inspect neighboring integration or adapter tests, build manifests, test-runner
configuration, fixture helpers, and CI commands. Record:

- the test framework and local style;
- how the target adapter is constructed;
- how external dependencies are provisioned and reset;
- the focused and broader test commands;
- how this repository distinguishes integration tests from E2E tests.

Do not assume Gradle, Kotest, Ktor, Testcontainers, Postgres, Flyway, Exposed,
or any named fixture until repository evidence establishes it. If no convention
exists, propose the smallest option compatible with the detected stack and get
approval before adding dependencies or build configuration.

## 2. Choose the seam

- Test behavior through a public repository, adapter, client, or application
  interface.
- Use the real boundary only where a fake would hide serialization, query,
  protocol, migration, transaction, or lifecycle behavior.
- Avoid full application boot; that belongs in `grillmester-e2e-tests`.
- Keep fixture state deterministic: initialize once at the appropriate scope,
  reset between cases, and close resources reliably.
- Use synthetic data without real personal data or secrets.

## 3. Implement and verify

Follow the discovered framework, naming, directory, lifecycle, and helper
patterns. Run the exact focused command, then the proportionate broader test
gate. Report commands, exit codes, and relevant output. Completion requires
fresh evidence that the real boundary was exercised through the public seam.
