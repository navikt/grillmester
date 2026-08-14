---
name: grillmester-e2e-tests
description: "Designs full-system tests that boot the application and prove an observable user or system flow across real boundaries. Use when a test must exercise the assembled app, an HTTP or message entry point, and its externally visible outcome; use grillmester-integration-tests for a narrow real adapter without full app boot."
---

# E2E Tests

Prove one complete flow through the assembled application. Discover the
repository's stack and test contract before selecting libraries, annotations,
fixtures, or commands.

## 1. Discover the test contract

Inspect repository evidence in this order:

1. Existing E2E or system tests and their nearest configuration.
2. Build manifests, task or script definitions, and test-runner configuration.
3. Application entry points and local boot fixtures.
4. Existing infrastructure fixtures, container setup, tags, and CI commands.

Record the discovered application boot path, test framework and style, fixture
lifecycle, E2E classification mechanism, and exact focused/full commands. Do
not infer Gradle, Kotest, Ktor, Jest, Playwright, Testcontainers, or any other
stack choice from this skill.

If no E2E convention exists, present the smallest option compatible with the
detected build and runtime and get approval before adding framework or build
configuration.

## 2. Choose the flow and boundaries

- Test one user or system flow through the running application.
- Enter through a production-shaped boundary such as HTTP, UI, CLI, or message
  ingestion.
- Assert externally observable outcomes, not internal calls.
- Use real infrastructure only where a substitute would hide the contract;
  reuse the repository's fixture strategy when one exists.
- Keep data deterministic and free of real personal data or secrets.

## 3. Implement in the repository's style

Follow the discovered framework, naming, tags, directories, lifecycle, and
helpers. Make setup visible enough that the flow remains readable. Cover the
relevant success and failure state without turning one E2E test into a complete
test suite.

## 4. Verify

Run the discovered focused E2E command first, then the repository's broader
E2E gate when proportionate. Report the exact commands, exit codes, and relevant
output. Completion requires fresh evidence that the test entered the assembled
application and observed the intended outcome.
