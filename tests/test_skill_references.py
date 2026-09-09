import unittest

from scripts.skill_references import rewrite_skill_references, skill_references


class SkillReferenceTests(unittest.TestCase):
    def test_unknown_native_loads_and_slash_calls_are_visible(self):
        text = "Load `grill-wth-docs` through the native skill tool. Use /missing-skill."
        self.assertEqual({"grill-wth-docs", "missing-skill"}, skill_references(text, {"review"}))

    def test_paths_links_examples_and_ordinary_words_are_preserved(self):
        source = (
            "Use `/triage` and `triage`. Already triaged; docs/triage.md; https://example.test/triage.\n"
            "[Review endpoint](/review) and `GET /review HTTP/1.1` and `` `/review` ``.\n"
            "```sh\nUse `/review`\n```\n"
        )
        result = rewrite_skill_references(source, {"triage": "issue assessment", "review": "`review`"})
        self.assertEqual(source.replace("`/triage` and `triage`", "issue assessment and issue assessment"), result)
        self.assertEqual({"triage"}, skill_references(source, {"review", "triage"}))

    def test_open_code_only_rewrites_exact_slash_code_spans(self):
        self.assertEqual("Use `review`; `review` is its ID.", rewrite_skill_references("Use `/review`; `review` is its ID.", {"review": "`review`"}, slash_only=True))


if __name__ == "__main__":
    unittest.main()
