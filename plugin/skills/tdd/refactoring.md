# Refactoring candidates

Load this reference only after a TDD cycle is green. Refactor in the language,
framework and module style established by the repository.

Look for:

- **Duplication** → extract one shared concept at the narrowest useful scope.
- **Long functions** → separate coherent responsibilities while keeping tests
  on the public interface.
- **Shallow modules** → merge or deepen them so a small interface hides more
  implementation complexity.
- **Feature envy** → move behavior next to the data and invariants it owns.
- **Primitive obsession** → introduce a domain value type when it prevents
  invalid states or argument mix-ups.
- **Existing friction** exposed by the new behavior → record it, but expand the
  current refactor only when it is necessary for the approved slice.

## Stack-sensitive checks

Inspect neighboring production code before applying a pattern. Depending on
repository evidence, useful moves may include:

- keeping transport or UI entry points focused on parsing, validation and
  response translation;
- collecting configuration and dependency composition behind one testable
  seam;
- replacing raw identifiers with the repository's established value-type
  pattern;
- moving protocol, persistence or framework details behind an adapter.

These are prompts, not universal layering rules. Preserve an established local
pattern when it already gives good locality and a stable public seam.

**Never refactor while a test is RED.** Reach GREEN first, run the discovered
focused test command, then refactor in small steps with fresh green evidence
between them.
