# When to substitute a boundary

Load this reference when a TDD cycle reaches time, randomness, network,
filesystem, process, database, broker or another system boundary. Discover the
repository's established fake, stub, mock and fixture patterns before choosing
a tool.

## Substitute system boundaries, not internal design

Common candidates:

- External HTTP or RPC services.
- Time and randomness.
- Filesystem, process or operating-system interaction.
- Slow or unavailable infrastructure when its real contract is not the subject
  of the current test.

Avoid substituting:

- The module's own classes merely to assert internal calls.
- Internal collaborators that should sit behind one deeper interface.
- A database, message broker or protocol adapter when its actual contract is
  what the test must prove and the repository already has a deterministic real
  fixture.

Rule of thumb: **if an internal collaborator needs a strict mock, the module
seam may be in the wrong place.**

## Choose the lightest honest test double

1. Use a fixed value for time, randomness or environment input.
2. Prefer a small hand-written fake when behavior matters.
3. Use a stub when one canned response is enough.
4. Use a mock only when the interaction itself is part of the external
   contract, such as retry count or required ordering.
5. Use the real adapter through `grillmester-integration-tests` when substitution would
   hide serialization, query, migration, transaction or protocol behavior.

Follow the library and lifecycle already used in neighboring tests. Do not add
a mocking library or container framework without approval.

## Design for testability

Prefer narrow, operation-specific ports over one generic conditional client:

```text
GOOD:
  ReservationLookup.isReserved(person)
  StatusLookup.currentStatus(person)

BAD:
  GenericClient.call(path, untypedBody)
```

Each focused port has one concrete contract, gives its fake one simple shape,
and makes the exercised dependency visible.

## HTTP boundaries

Use the detected HTTP client's supported fake transport or mock server so the
production serialization and error handling remain in the path. Examples may
include an in-memory transport, a local mock server or a framework test client,
but choose one only after repository evidence establishes the stack.

Assert the observable client behavior. Avoid testing that a private helper
constructed a request in a particular sequence unless wire shape or ordering is
the contract.
