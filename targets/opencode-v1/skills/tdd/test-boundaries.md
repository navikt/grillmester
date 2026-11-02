# Test boundaries

Choose the highest seam that is still fast enough for the loop. Start with the
repository's own convention: neighboring tests, build files, runner
configuration, fixture helpers and CI show how it separates module,
integration and full-application tests, and which command runs each.

| What the test must show | Seam |
|---|---|
| The logic gives the right result. | The module's public interface, with fakes only at system boundaries. |
| An adapter really works against its dependency: database, HTTP client, message broker or filesystem. | The real adapter through its public interface, without booting the whole application. |
| The entry point, wiring and outcome work together. | The running application through a production-shaped entry: HTTP, UI, CLI or message ingestion. |

## A real adapter

Use the real dependency only where a fake would hide serialization, queries,
protocols, migrations, transactions or lifecycle behavior. Reuse the
repository's fixture strategy, such as containers or an embedded server.
Initialize at the right scope, reset between cases and close resources.

## The running application

Prove one user or system flow through the assembled application and assert
outcomes a user or caller can observe, not internal calls. Cover the success
path and the failure that matters. Keep it to that flow and cover variations
at a lower seam.

## For both

- Use synthetic data without real personal data or secrets.
- Keep data and time deterministic.
- When the repository has no convention for the boundary, propose the smallest
  option that fits the stack and get approval before adding a framework or
  build configuration.
- Report the focused command, its result and exit code, and show that the test
  reached the real boundary.
