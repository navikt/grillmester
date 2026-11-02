# Smell baseline

A fixed baseline of code smells from Martin Fowler's *Refactoring* that applies
even when a repository documents nothing. Report each one as a judgement call,
such as "possible feature envy", never as a hard violation. A documented
repository rule always wins, and anything a linter or formatter already
enforces is out of scope.

Report only smells the diff introduces or worsens, a few at most, and none for
text-only changes. Report a smell rather than refactor it, unless the fix is
small and inside the task's scope.

- **Mysterious name:** a name that hides what the thing does or holds. Rename
  it; if no honest name comes, the design is unclear.
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
