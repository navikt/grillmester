"""Read and adapt explicit skill references without changing examples or paths."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable

IDENTIFIER = re.compile(r"/?[a-z][a-z0-9-]*\Z")
CODE_SPAN = re.compile(r"(?<!`)(`+)([^\n]*?)\1(?!`)")
LINK = re.compile(r"!?\[[^\]\n]*\]\([^\n]*?\)")
FENCE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")


def transform_prose(text: str, transform: Callable[[str], str]) -> str:
    """Keep fenced examples and Markdown links byte-identical."""
    result: list[str] = []
    fence: str | None = None
    for line in text.splitlines(keepends=True):
        marker = FENCE.match(line)
        if marker:
            run = marker.group(1)
            if fence is None:
                fence = run
            elif run[0] == fence[0] and len(run) >= len(fence):
                fence = None
            result.append(line)
        elif fence is not None:
            result.append(line)
        else:
            start = 0
            for link in LINK.finditer(line):
                result.append(transform(line[start:link.start()]))
                result.append(link.group())
                start = link.end()
            result.append(transform(line[start:]))
    return "".join(result)


def rewrite_skill_references(text: str, replacements: dict[str, str], *, slash_only: bool = False) -> str:
    def replace_span(match: re.Match[str]) -> str:
        if match.group(1) != "`":
            return match.group()
        value = match.group(2)
        if not IDENTIFIER.fullmatch(value) or (slash_only and not value.startswith("/")):
            return match.group()
        return replacements.get(value.removeprefix("/"), match.group())

    return transform_prose(text, lambda part: CODE_SPAN.sub(replace_span, part))


def skill_references(text: str, known_ids: Iterable[str]) -> set[str]:
    """Include unknown explicit calls so a misspelled skill cannot disappear."""
    known = set(known_ids)
    found: set[str] = set()

    def inspect(part: str) -> str:
        for match in CODE_SPAN.finditer(part):
            value = match.group(2)
            if match.group(1) != "`" or not IDENTIFIER.fullmatch(value):
                continue
            name = value.removeprefix("/")
            before, after = part[:match.start()], part[match.end():]
            named_load = re.search(r"\b(?:load|invoke|activate|consult)\s+(?:the\s+)?$", before, re.I)
            skill_context = re.match(r"\s+skill\b|\s+(?:through|with|using)\b[^.!?\n]*\bskill\b", after, re.I)
            if value.startswith("/") or name in known or (named_load and skill_context):
                found.add(name)
        # Legacy prose calls are still diagnosed, but never treated as paths.
        for match in re.finditer(r"\b(?:use|load|invoke|run|call|consult)\s+(?:the\s+|a\s+)?/([a-z][a-z0-9-]*)(?![\w/-]|\.[\w])", part, re.I):
            found.add(match.group(1))
        return part

    transform_prose(text, inspect)
    return found
