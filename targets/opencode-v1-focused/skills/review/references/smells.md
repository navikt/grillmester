# Smells and refactoring

A fixed baseline of code smells from Martin Fowler's *Refactoring* that applies
even when a repository documents nothing. A smell is a judgement call, such as
"possible feature envy", never a hard violation. A documented repository rule
always wins, and anything a linter or formatter already enforces is out of
scope.

Consider only smells the diff introduces or worsens, a few at most, and none
for text-only changes. As the writer, fix them in the code you added or changed,
and report what lies outside the task. As a read-only reviewer, report them.

- **Mysterious name:** a name that hides what the thing does or holds. Rename
  it; if no honest name comes, the design is unclear.
- **Long function:** a function that does several things, or whose parts need
  comments to tell them apart. Extract the parts that deserve their own name.
  Length alone is no reason: thin helpers that only shorten it make it worse.
- **Large class or module:** a class or file that has taken on several
  responsibilities. Split it along what changes together.
- **Long parameter list:** many parameters, or a flag that switches behavior.
  Give values that belong together a type, or split the function.
- **Shallow module:** an interface about as complex as what it hides. Merge or
  deepen it so a small interface hides more.
- **Duplicated code:** the same logic shape in more than one place in the
  change. Extract the shared shape and call it from both.
- **Feature envy:** a function that uses another module's data more than its
  own. Move it next to that data.
- **Data clumps:** the same few fields or parameters that keep travelling
  together. Give them one type.
- **Primitive obsession:** a primitive or string standing in for a domain
  concept. Give the concept its own small type.
- **Repeated switches:** the same branching on the same type in several
  places. Use one shared map or polymorphism.
- **Shotgun surgery:** one logical change that forces scattered edits. Gather
  what changes together.
- **Divergent change:** one module edited for several unrelated reasons. Split
  it so each part changes for one reason.
- **Speculative generality:** abstractions, parameters or hooks for needs
  nobody has. Remove them until a real need appears.
- **Message chains:** long `a.b().c().d()` navigation. Hide the walk behind one
  call on the first object.
- **Middle man:** a class or function that mostly delegates. Call the target
  directly.
- **Refused bequest:** a subtype that ignores most of what it inherits. Use
  composition instead.

## Refactor safely

Never refactor while a test is red. Reach green, run the focused tests, and
then refactor in small steps with fresh green evidence between them. Keep tests
on the public interface. Record friction the new behavior exposes, and widen the
refactor only when the task needs it.

Follow the repository's language, framework and module style, and read
neighboring production code before applying a pattern. Depending on what you
find, useful moves include:

- keeping transport or UI entry points focused on parsing, validation and
  response translation;
- collecting configuration and dependency composition behind one testable
  seam;
- replacing raw identifiers with the repository's established value-type
  pattern;
- moving protocol, persistence or framework details behind an adapter.

These are prompts, not universal layering rules. Preserve an established local
pattern when it already gives good locality and a stable public seam.
