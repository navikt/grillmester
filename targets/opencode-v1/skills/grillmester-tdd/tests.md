# Good and bad tests

Load this reference when choosing the seam and assertion shape for a TDD cycle.
The examples are language-neutral patterns. Translate them into the framework,
naming and fixture style discovered in the target repository.

## Discover before choosing syntax

Inspect neighboring tests and runner configuration. Establish:

- the framework and assertion library;
- naming and directory conventions;
- the focused-test selector;
- available fakes, fixtures and application harnesses;
- which tests are unit, integration or full-system tests.

Do not introduce a new framework merely because an example in this reference
resembles it.

## Good tests

Good tests exercise behavior through a public interface and assert an outcome a
caller can observe.

```text
test "publishing an accepted message returns Sent" {
  publisher = RecordingPublisher()
  handler = MessageHandler(publisher)

  outcome = handler.handle(syntheticMessage())

  expect outcome == Sent
  expect publisher.published contains the accepted payload
}
```

Characteristics:

- Tests behavior callers care about.
- Uses only the public interface.
- Survives internal refactoring.
- Describes what happens, not how collaborators are arranged.
- Keeps one coherent behavioral claim per test.
- Uses synthetic data without real personal data or secrets.

Test names should read like specifications and follow the repository's artifact
language. Preserve established domain terms and contract field names exactly.

## Bad tests

Interaction-only tests often couple behavior to internal structure:

```text
test "handle calls publisher" {
  publisher = strictMock()
  handler = MessageHandler(publisher)

  handler.handle(syntheticMessage())

  verify publisher.publish was called exactly once
}
```

Red flags:

- Mocking internal collaborators.
- Testing private functions.
- Asserting internal call count or ordering with no contract reason.
- Breaking after a refactor that preserves behavior.
- Naming the implementation step rather than the outcome.

Another common mistake is going around the public interface to inspect storage:

```text
BAD:
  repository.save(record)
  query the storage table directly
  expect one row

GOOD:
  repository.save(record)
  expect repository.load(record.id) == record
```

The direct query is appropriate only when the storage schema itself is the
contract under test. Otherwise assert through the seam.

## Pick the smallest honest test level

- **Pure behavior:** use the repository's fast unit-test style.
- **Serialization, query, transaction or protocol contract:** use the real
  adapter through `grillmester-integration-tests` when a fake would hide the risk.
- **Application composition or complete user/system flow:** use `grillmester-e2e-tests`.
- **Hard-to-reproduce bug:** use `grillmester-diagnosing-bugs` to build a tight loop before
  turning the minimized reproduction into a regression test.

When a boundary needs substitution, load [mocking.md](mocking.md). The selected
substitute must preserve the behavior this test is meant to prove.
