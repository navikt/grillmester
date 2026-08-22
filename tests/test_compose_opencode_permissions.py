from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "grillmester_compose_opencode_permissions",
    ROOT / "scripts/compose_opencode_permissions.py",
)
assert SPEC and SPEC.loader
COMPOSER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = COMPOSER
SPEC.loader.exec_module(COMPOSER)


class ComposeOpenCodePermissionsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.config = self.root / "config"
        shutil.copytree(ROOT / "targets/opencode-v1", self.config)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def safe_config(self, **values: object) -> dict[str, object]:
        return {
            "autoupdate": False,
            "share": "disabled",
            "plugin": [],
            **values,
        }

    def test_composes_role_policy_with_unknown_fallbacks_and_user_denies(self) -> None:
        restrictions = {
            "permission": {
                "edit": "deny",
                "bash": {"danger *": "deny", "git status": "allow"},
                "github_*": "deny",
            },
            "agent": {
                "grillmester": {
                    "permission": {
                        "webfetch": "deny",
                        "task": {"untrusted": "deny"},
                    }
                },
                "kokk": {"permission": {"bash": {"sudo *": "deny"}}},
            },
        }
        resolved = self.safe_config(
            mcp={"disabled": {"type": "local", "enabled": False}}
        )

        policy = COMPOSER.compose_policy(self.config, resolved, [restrictions])
        content = json.loads(policy.config_content)

        self.assertEqual("ask", content["permission"]["*"])
        grillmester = policy.agents["grillmester"]
        self.assertEqual("deny", grillmester["edit"])
        self.assertEqual("deny", grillmester["github_*"])
        self.assertEqual("deny", grillmester["webfetch"])
        self.assertEqual("deny", grillmester["bash"]["danger *"])
        self.assertNotIn("git status", grillmester["bash"])
        self.assertEqual("deny", grillmester["task"]["untrusted"])
        self.assertEqual("allow", grillmester["task"]["kokk"])
        self.assertEqual("allow", grillmester["task"]["grill-inspektor"])
        self.assertEqual("allow", grillmester["task"]["researcher"])

        kokk = policy.agents["kokk"]
        self.assertEqual("deny", kokk["edit"])
        self.assertEqual("deny", kokk["bash"]["sudo *"])
        inspector = policy.agents["grill-inspektor"]
        self.assertEqual("ask", inspector["bash"]["*"])
        self.assertEqual("deny", inspector["bash"]["danger *"])
        self.assertEqual("deny", inspector["edit"])

        researcher = policy.agents["researcher"]
        self.assertEqual("deny", researcher["*"])
        for key in ("read", "glob", "grep", "list"):
            self.assertIn(key, researcher)
        self.assertEqual("allow", researcher["glob"])
        self.assertEqual("allow", researcher["webfetch"])
        self.assertEqual("allow", researcher["websearch"])
        self.assertEqual("ask", researcher["read"]["*.env"])
        self.assertEqual("allow", researcher["read"]["*.env.example"])

        skill = grillmester["skill"]
        self.assertEqual("ask", skill["*"])
        self.assertEqual("allow", skill["grillmester-review"])
        for skill_id in (
            "grillmester-doctor",
            "grillmester-grill-me",
            "grillmester-grill-with-docs",
            "grillmester-handoff",
        ):
            self.assertEqual("ask", skill[skill_id])

        external = grillmester["external_directory"]
        self.assertEqual("ask", external["*"])
        self.assertTrue(
            any(
                pattern.endswith("/skills/grillmester-review/*") and action == "allow"
                for pattern, action in external.items()
            )
        )

    def test_wildcard_deny_is_conservatively_terminal(self) -> None:
        policy = COMPOSER.compose_policy(
            self.config,
            self.safe_config(),
            [{
                "permission": {"*": {"*": "deny", "read": "allow"}},
            }],
        )
        for permission in policy.agents.values():
            self.assertEqual({"*": "deny"}, permission)

    def test_generated_wildcard_fallback_must_precede_exact_tool_rules(self) -> None:
        permission = {"read": "allow", "*": "ask"}
        with self.assertRaisesRegex(
            COMPOSER.PermissionCompositionError, "must be the first"
        ):
            COMPOSER._append_constraints(permission, (), fallback="ask")

    def test_resolved_ambient_permissions_are_never_copied_to_child_content(self) -> None:
        sentinel = "resolved-file-secret-sentinel"
        policy = COMPOSER.compose_policy(
            self.config,
            self.safe_config(
                permission={"bash": {sentinel: "deny"}},
                agent={"kokk": {"permission": {sentinel: "deny"}}},
            ),
        )
        serialized = policy.config_content + json.dumps(policy.agents, sort_keys=True)
        self.assertNotIn(sentinel, serialized)

    def test_bounded_config_probe_keeps_structure_but_defers_agent_permissions(self) -> None:
        policy = COMPOSER.compose_policy(
            self.config,
            self.safe_config(
                agent={
                    "kokk": {
                        "model": "private/model",
                        "variant": "careful",
                    }
                }
            ),
            runtime_agent="grillmester",
        )
        full = json.loads(policy.config_content)
        probe = json.loads(COMPOSER.build_bounded_config_probe_content(policy))

        self.assertEqual(
            {key: value for key, value in full.items() if key != "agent"},
            {key: value for key, value in probe.items() if key != "agent"},
        )
        for agent_id in policy.agents:
            self.assertNotIn("permission", probe["agent"][agent_id])
            self.assertEqual(
                {
                    field: value
                    for field, value in full["agent"][agent_id].items()
                    if field != "permission"
                },
                probe["agent"][agent_id],
            )
        for agent_id in (*COMPOSER.DISABLED_NATIVE_AGENTS, *COMPOSER.HIDDEN_NATIVE_AGENTS):
            self.assertEqual(full["agent"][agent_id], probe["agent"][agent_id])
        restored = json.loads(json.dumps(probe))
        for agent_id in policy.agents:
            restored["agent"][agent_id]["permission"] = full["agent"][agent_id][
                "permission"
            ]
        self.assertEqual(full, restored)
        self.assertEqual("private/model", probe["agent"]["kokk"]["model"])
        self.assertEqual("careful", probe["agent"]["kokk"]["variant"])
        self.assertLess(
            len(COMPOSER.build_bounded_config_probe_content(policy)),
            len(policy.config_content),
        )

        drifted = json.loads(policy.config_content)
        drifted["agent"]["kokk"]["permission"] = {"*": "allow"}
        with self.assertRaisesRegex(
            COMPOSER.PermissionCompositionError, "permission drifted"
        ):
            COMPOSER.build_bounded_config_probe_content(
                replace(
                    policy,
                    config_content=json.dumps(drifted, separators=(",", ":")),
                )
            )

        extended = json.loads(policy.config_content)
        extended["agent"]["kokk"]["temperature"] = 1
        with self.assertRaisesRegex(
            COMPOSER.PermissionCompositionError, "unexpected probe fields"
        ):
            COMPOSER.build_bounded_config_probe_content(
                replace(
                    policy,
                    config_content=json.dumps(extended, separators=(",", ":")),
                )
            )

    def test_per_agent_non_deny_wildcard_fails_closed(self) -> None:
        with self.assertRaisesRegex(
            COMPOSER.PermissionCompositionError, "allow-only wildcard"
        ):
            COMPOSER.compose_policy(
                self.config,
                self.safe_config(),
                [{
                    "agent": {
                        "kokk": {"permission": {"*": "allow", "bash": "deny"}}
                    },
                }],
            )

    def test_enabled_plugins_and_mcp_are_rejected(self) -> None:
        for resolved, message in (
            (self.safe_config(plugin=["example"]), "plugins"),
            (self.safe_config(plugin_origins=[{"spec": "example"}]), "plugins"),
            (self.safe_config(mcp={"github": {"type": "remote"}}), "enabled OpenCode MCP"),
        ):
            with self.subTest(resolved=resolved), self.assertRaisesRegex(
                COMPOSER.PermissionCompositionError, message
            ):
                COMPOSER.compose_policy(self.config, resolved)

    def test_rewrite_resets_each_permission_key_without_touching_body(self) -> None:
        policy = COMPOSER.compose_policy(self.config, self.safe_config())
        before = (self.config / "agents/grillmester.md").read_text(encoding="utf-8")
        body = before.split("\n---\n", 1)[1]

        COMPOSER.rewrite_staged_agents(self.config, policy)

        after = (self.config / "agents/grillmester.md").read_text(encoding="utf-8")
        self.assertEqual(body, after.split("\n---\n", 1)[1])
        parsed = COMPOSER.parse_generated_agent(
            self.config / "agents/grillmester.md"
        )
        self.assertEqual(set(policy.reset_keys["grillmester"]), set(parsed.permission))
        self.assertTrue(all(action == "deny" for action in parsed.permission.values()))

    def test_effective_validation_catches_late_widening(self) -> None:
        tool_output = "/tmp/cplt/data/opencode/tool-output/*"
        intended = {
            "read": {"*": "allow", "*.env": "ask"},
            "edit": "deny",
            "task": {"*": "deny", "kokk": "allow"},
            "external_directory": "ask",
        }
        cplt_prefix = [
            {
                "permission": "external_directory",
                "pattern": "/tmp/cplt/read-b/*",
                "action": "allow",
            },
            {
                "permission": "external_directory",
                "pattern": "/tmp/cplt/read-a/*",
                "action": "allow",
            },
            {
                "permission": "external_directory",
                "pattern": (
                    "/Users/test/Library/Caches/cplt/tmp/"
                    "0123456789abcdef0123456789abcdef/opencode/*"
                ),
                "action": "allow",
            },
            {"permission": "bash", "pattern": "*", "action": "deny"},
            {"permission": "bash", "pattern": "safe", "action": "deny"},
        ]
        good = {
            "name": "grillmester",
            "description": "expected",
            "mode": "primary",
            "hidden": False,
            "native": False,
            "prompt": "expected prompt",
            "permission": [
                *cplt_prefix,
                {"permission": "*", "pattern": "*", "action": "ask"},
                {"permission": "read", "pattern": "*", "action": "allow"},
                {"permission": "read", "pattern": "*.env", "action": "ask"},
                {"permission": "edit", "pattern": "*", "action": "deny"},
                {"permission": "task", "pattern": "*", "action": "deny"},
                {"permission": "task", "pattern": "kokk", "action": "allow"},
                {
                    "permission": "external_directory",
                    "pattern": "*",
                    "action": "ask",
                },
                {
                    "permission": "external_directory",
                    "pattern": tool_output,
                    "action": "allow",
                },
            ],
        }
        contract = {
            "description": "expected",
            "mode": "primary",
            "hidden": False,
            "prompt": "expected prompt",
        }
        digest = COMPOSER.validate_effective_agent(
            "grillmester", good, intended, contract, tool_output
        )
        self.assertRegex(digest, r"^[0-9a-f]{64}$")
        equivalent = json.loads(json.dumps(good))
        equivalent["permission"][:3] = reversed(equivalent["permission"][:3])
        equivalent["permission"][0]["pattern"] = (
            "/Users/test/Library/Caches/cplt/tmp/"
            "fedcba9876543210fedcba9876543210/opencode/*"
        )
        self.assertEqual(
            digest,
            COMPOSER.validate_effective_agent(
                "grillmester", equivalent, intended, contract, tool_output
            ),
        )
        noncommutative = json.loads(json.dumps(good))
        noncommutative["permission"][0]["action"] = "deny"
        self.assertNotEqual(
            digest,
            COMPOSER.validate_effective_agent(
                "grillmester", noncommutative, intended, contract, tool_output
            ),
        )
        deny_reordered = json.loads(json.dumps(good))
        deny_reordered["permission"][3:5] = reversed(
            deny_reordered["permission"][3:5]
        )
        self.assertNotEqual(
            digest,
            COMPOSER.validate_effective_agent(
                "grillmester", deny_reordered, intended, contract, tool_output
            ),
        )
        unsafe_tool_output = json.loads(json.dumps(good))
        unsafe_tool_output["permission"][-1]["pattern"] = (
            "../escape/tool-output/*"
        )
        with self.assertRaisesRegex(
            COMPOSER.PermissionCompositionError,
            "exact managed tool-output rule",
        ):
            COMPOSER.validate_effective_agent(
                "grillmester", unsafe_tool_output, intended, contract, tool_output
            )
        backslash_tool_output = json.loads(json.dumps(good))
        backslash_tool_output["permission"][-1]["pattern"] = tool_output.replace(
            "/", "\\"
        )
        with self.assertRaisesRegex(
            COMPOSER.PermissionCompositionError,
            "exact managed tool-output rule",
        ):
            COMPOSER.validate_effective_agent(
                "grillmester",
                backslash_tool_output,
                intended,
                contract,
                tool_output,
            )
        backslash_scratch = json.loads(json.dumps(good))
        backslash_scratch["permission"][2]["pattern"] = backslash_scratch[
            "permission"
        ][2]["pattern"].replace("/", "\\")
        self.assertNotEqual(
            digest,
            COMPOSER.validate_effective_agent(
                "grillmester",
                backslash_scratch,
                intended,
                contract,
                tool_output,
            ),
        )
        malformed = json.loads(json.dumps(good))
        malformed["permission"][0]["source"] = "ambient"
        with self.assertRaisesRegex(
            COMPOSER.PermissionCompositionError, "malformed rules"
        ):
            COMPOSER.validate_effective_agent(
                "grillmester", malformed, intended, contract, tool_output
            )
        malformed_action = json.loads(json.dumps(good))
        malformed_action["permission"][0]["action"] = []
        with self.assertRaisesRegex(
            COMPOSER.PermissionCompositionError, "malformed rules"
        ):
            COMPOSER.validate_effective_agent(
                "grillmester",
                malformed_action,
                intended,
                contract,
                tool_output,
            )

        native_override = json.loads(json.dumps(good))
        native_override["native"] = True
        with self.assertRaisesRegex(
            COMPOSER.PermissionCompositionError, "native override"
        ):
            COMPOSER.validate_effective_agent(
                "grillmester", native_override, intended, contract, tool_output
            )

        widened = json.loads(json.dumps(good))
        widened["permission"].insert(
            -1,
            {"permission": "edit", "pattern": "*", "action": "allow"}
        )
        with self.assertRaisesRegex(
            COMPOSER.PermissionCompositionError, "exact composed rule map"
        ):
            COMPOSER.validate_effective_agent(
                "grillmester", widened, intended, contract, tool_output
            )

        changed_prompt = json.loads(json.dumps(good))
        changed_prompt["prompt"] = "managed override"
        with self.assertRaisesRegex(
            COMPOSER.PermissionCompositionError, "changed generated prompt"
        ):
            COMPOSER.validate_effective_agent(
                "grillmester", changed_prompt, intended, contract, tool_output
            )

    def test_rejects_executable_provider_skill_lsp_and_formatter_surfaces(self) -> None:
        cases = (
            ({"skills": {"paths": ["../skills"]}}, "skills.paths"),
            ({"skills": {"urls": ["https://example.test/skills"]}}, "skills.urls"),
            (
                {
                    "provider": {
                        "local": {
                            "npm": "file:///tmp/provider.js",
                            "models": {"model": {}},
                        }
                    }
                },
                "must be omitted or exactly",
            ),
            (
                {"provider": {"local": {"models": {"model": {}}}}},
                "must resolve through exactly",
            ),
            ({"lsp": {"evil": {"command": ["/tmp/evil"]}}}, "executable"),
            ({"formatter": True}, "disabled-only"),
        )
        for extension, message in cases:
            with self.subTest(extension=extension), self.assertRaisesRegex(
                COMPOSER.PermissionCompositionError, message
            ):
                COMPOSER.require_no_external_extensions(
                    self.safe_config(**extension)
                )

        COMPOSER.require_no_external_extensions(
            self.safe_config(
                provider={
                    "local": {
                        "npm": "@ai-sdk/openai-compatible",
                        "models": {"model": {}},
                    }
                },
                lsp={"unused": {"disabled": True}},
                formatter=False,
            )
        )

    def test_resolved_extension_diagnostics_are_key_and_value_opaque(self) -> None:
        sentinel = "resolved-extension-key-secret-sentinel"
        sentinel_digest = hashlib.sha256(sentinel.encode()).hexdigest()
        configs = (
            self.safe_config(mcp={sentinel: {"type": "remote"}}),
            self.safe_config(
                provider={sentinel: {"npm": "file:///tmp/provider.js"}}
            ),
            self.safe_config(
                provider={
                    "safe-provider": {
                        "npm": COMPOSER.SAFE_PROVIDER_NPM,
                        "models": {
                            sentinel: {
                                "provider": {"npm": "file:///tmp/model.js"}
                            }
                        },
                    }
                }
            ),
            self.safe_config(lsp={sentinel: {"command": ["/tmp/evil"]}}),
            self.safe_config(formatter={sentinel: {"command": ["/tmp/evil"]}}),
        )
        for config in configs:
            with self.subTest(config=config), self.assertRaises(
                COMPOSER.PermissionCompositionError
            ) as failure:
                COMPOSER.require_no_external_extensions(config)
            chain = " | ".join(
                str(error)
                for error in (failure.exception, failure.exception.__cause__)
                if error is not None
            )
            self.assertNotIn(sentinel, chain)
            self.assertNotIn(sentinel_digest, chain)

    def test_rejects_every_pinned_custom_provider_loader_id(self) -> None:
        expected = {
            "amazon-bedrock",
            "anthropic",
            "azure",
            "azure-cognitive-services",
            "cerebras",
            "cloudflare-ai-gateway",
            "cloudflare-workers-ai",
            "github-copilot",
            "gitlab",
            "google-vertex",
            "google-vertex-anthropic",
            "kilo",
            "llmgateway",
            "meta",
            "nvidia",
            "opencode",
            "openai",
            "openrouter",
            "sap-ai-core",
            "snowflake-cortex",
            "vercel",
            "xai",
            "zenmux",
        }
        self.assertEqual(expected, COMPOSER.RESERVED_PROVIDER_IDS)
        for provider_id in sorted(expected):
            with self.subTest(provider_id=provider_id), self.assertRaisesRegex(
                COMPOSER.PermissionCompositionError, "built-in OpenCode"
            ):
                COMPOSER.require_no_external_extensions(
                    self.safe_config(
                        provider={
                            provider_id: {
                                "npm": "@ai-sdk/openai-compatible",
                                "models": {"model": {}},
                            }
                        }
                    )
                )

    def test_target_command_contract_rejects_post_content_override(self) -> None:
        policy = COMPOSER.compose_policy(self.config, self.safe_config())
        resolved = {"command": json.loads(json.dumps(policy.command_contracts))}
        digest = COMPOSER.validate_target_commands(
            resolved, policy.command_contracts
        )
        self.assertRegex(digest, r"^[0-9a-f]{64}$")
        resolved["command"]["grillmester-review"]["template"] = "shadowed"
        with self.assertRaisesRegex(
            COMPOSER.PermissionCompositionError, "does not match"
        ):
            COMPOSER.validate_target_commands(
                resolved, policy.command_contracts
            )

        resolved = {
            "command": {
                **json.loads(json.dumps(policy.command_contracts)),
                "ambient-shell": {"template": "!touch /tmp/must-not-run"},
            }
        }
        with self.assertRaisesRegex(
            COMPOSER.PermissionCompositionError, "unexpected.*command"
        ):
            COMPOSER.validate_target_commands(
                resolved, policy.command_contracts
            )

    def test_baseline_rejects_ambient_commands_and_unknown_agents(self) -> None:
        for extension, message in (
            (
                {"command": {"ambient-shell": {"template": "!touch /tmp/pwned"}}},
                "ambient.*command",
            ),
            (
                {"agent": {"ambient": {"permission": {"bash": "allow"}}}},
                "unknown.*agent",
            ),
            (
                {"agent": {"kokk": {"prompt": "replace generated prompt"}}},
                "unsupported.*agent",
            ),
        ):
            with self.subTest(extension=extension), self.assertRaisesRegex(
                COMPOSER.PermissionCompositionError, message
            ):
                COMPOSER.compose_policy(
                    self.config, self.safe_config(**extension)
                )

        policy = COMPOSER.compose_policy(
            self.config,
            self.safe_config(
                provider={
                    "local": {
                        "npm": "@ai-sdk/openai-compatible",
                        "models": {"model": {}},
                    }
                },
                agent={
                    "kokk": {
                        "permission": {"bash": "deny"},
                        "model": "private/model",
                        "variant": "careful",
                    }
                }
            ),
        )
        self.assertEqual("ask", policy.agents["kokk"]["bash"])
        isolated = json.loads(policy.config_content)
        self.assertEqual("private/model", isolated["agent"]["kokk"]["model"])
        self.assertEqual("careful", isolated["agent"]["kokk"]["variant"])
        self.assertEqual(
            "@ai-sdk/openai-compatible",
            isolated["provider"]["local"]["npm"],
        )
        self.assertEqual(["local"], isolated["enabled_providers"])
        self.assertEqual([], isolated["disabled_providers"])
        COMPOSER.validate_target_agent_ids(
            isolated,
            policy.agents,
            policy.agent_contracts,
            policy.runtime_agent,
        )
        changed_variant = json.loads(policy.config_content)
        changed_variant["agent"]["kokk"]["variant"] = "fast"
        with self.assertRaisesRegex(
            COMPOSER.PermissionCompositionError, "changed variant"
        ):
            COMPOSER.validate_target_agent_ids(
                changed_variant,
                policy.agents,
                policy.agent_contracts,
                policy.runtime_agent,
            )
        self.assertRegex(
            COMPOSER.validate_provider_contract(isolated, isolated["provider"]),
            r"^[0-9a-f]{64}$",
        )
        widened = json.loads(policy.config_content)
        widened["provider"]["late"] = {
            "npm": "@ai-sdk/openai-compatible",
            "models": {"model": {}},
        }
        with self.assertRaisesRegex(
            COMPOSER.PermissionCompositionError, "exact selected provider"
        ):
            COMPOSER.validate_provider_contract(widened, isolated["provider"])
        disabled = json.loads(policy.config_content)
        disabled["disabled_providers"] = ["local"]
        with self.assertRaisesRegex(
            COMPOSER.PermissionCompositionError, "disabled_providers"
        ):
            COMPOSER.validate_provider_contract(disabled, isolated["provider"])

    def test_final_agent_contract_rejects_extra_selectable_agent(self) -> None:
        policy = COMPOSER.compose_policy(self.config, self.safe_config())
        resolved = {"agent": json.loads(policy.config_content)["agent"]}
        digest = COMPOSER.validate_target_agent_ids(
            resolved,
            policy.agents,
            policy.agent_contracts,
            policy.runtime_agent,
        )
        self.assertRegex(digest, r"^[0-9a-f]{64}$")
        for agent_id in COMPOSER.DISABLED_NATIVE_AGENTS:
            resolved["agent"][agent_id].update(
                {"options": {}, "permission": {"read": "deny"}}
            )
        for agent_id in COMPOSER.HIDDEN_NATIVE_AGENTS:
            resolved["agent"][agent_id]["options"] = {}
        COMPOSER.validate_target_agent_ids(
            resolved,
            policy.agents,
            policy.agent_contracts,
            policy.runtime_agent,
        )
        weakened = json.loads(json.dumps(resolved))
        weakened["agent"][COMPOSER.DISABLED_NATIVE_AGENTS[0]]["disable"] = False
        with self.assertRaisesRegex(
            COMPOSER.PermissionCompositionError, "is not disabled"
        ):
            COMPOSER.validate_target_agent_ids(
                weakened,
                policy.agents,
                policy.agent_contracts,
                policy.runtime_agent,
            )
        resolved["agent"]["ambient"] = {"mode": "primary"}
        with self.assertRaisesRegex(
            COMPOSER.PermissionCompositionError, "unexpected.*agent"
        ):
            COMPOSER.validate_target_agent_ids(
                resolved,
                policy.agents,
                policy.agent_contracts,
                policy.runtime_agent,
            )

    def test_only_selected_generated_primary_is_enabled(self) -> None:
        policy = COMPOSER.compose_policy(
            self.config, self.safe_config(), runtime_agent="barista"
        )
        agents = json.loads(policy.config_content)["agent"]
        self.assertNotIn("disable", agents["barista"])
        for agent_id in ("designer", "doctor-who", "grillmester"):
            self.assertIs(True, agents[agent_id]["disable"])
        for agent_id in COMPOSER.DISABLED_NATIVE_AGENTS:
            self.assertEqual({"disable": True}, agents[agent_id])
        for agent_id in COMPOSER.HIDDEN_NATIVE_AGENTS:
            self.assertEqual({"permission": {"*": "deny"}}, agents[agent_id])
        self.assertEqual(
            ("barista", "grill-inspektor", "kokk", "researcher"),
            policy.enabled_agent_ids,
        )

    def test_designer_server_patterns_never_preallow_consumer_javascript(self) -> None:
        policy = COMPOSER.compose_policy(
            self.config, self.safe_config(), runtime_agent="designer"
        )
        bash = policy.agents["designer"]["bash"]
        self.assertIsInstance(bash, dict)
        assert isinstance(bash, dict)
        for pattern in COMPOSER.DESIGNER_REVIEWED_SERVER_PATTERNS:
            self.assertEqual("ask", bash[pattern])
        rules = COMPOSER._rules_from_permission({"bash": bash})
        self.assertNotEqual(
            "allow",
            COMPOSER.evaluate_rules(
                rules,
                "bash",
                "node scripts/server.js --project-dir /consumer; touch /tmp/owned",
            ),
        )
        self.assertNotEqual(
            "allow",
            COMPOSER.evaluate_rules(
                rules,
                "bash",
                "node /consumer/grillmester-design-prototype/scripts/server.js "
                "--project-dir /consumer",
            ),
        )
        self.assertEqual("deny", bash["node scripts/server.js * --cleanup-all*"])
        self.assertEqual(
            "deny",
            bash[
                "node *grillmester-design-prototype/scripts/server.js * --cleanup-all*"
            ],
        )

    def test_every_managed_agent_terminally_denies_native_plan_tools(self) -> None:
        policy = COMPOSER.compose_policy(self.config, self.safe_config())

        for agent_id, permission in policy.agents.items():
            with self.subTest(agent=agent_id):
                rules = COMPOSER._rules_from_permission(permission)
                for tool in COMPOSER.DISABLED_PLAN_TOOLS:
                    self.assertEqual("deny", permission[tool])
                    self.assertEqual(
                        "deny", COMPOSER.evaluate_rules(rules, tool, "*")
                    )

    def test_hidden_native_agent_effective_policy_is_terminal_deny(self) -> None:
        tool_output = "/tmp/cplt/data/opencode/tool-output/*"
        resolved = {
            "name": "summary",
            "native": True,
            "hidden": True,
            "permission": [
                {
                    "permission": "external_directory",
                    "pattern": "/tmp/cplt/read-b/*",
                    "action": "allow",
                },
                {
                    "permission": "external_directory",
                    "pattern": "/tmp/cplt/read-a/*",
                    "action": "allow",
                },
                {"permission": "*", "pattern": "*", "action": "ask"},
                {"permission": "*", "pattern": "*", "action": "deny"},
                {
                    "permission": "external_directory",
                    "pattern": tool_output,
                    "action": "allow",
                },
            ],
        }
        digest = COMPOSER.validate_hidden_native_agent(
            "summary", resolved, tool_output
        )
        self.assertRegex(digest, r"^[0-9a-f]{64}$")
        equivalent = json.loads(json.dumps(resolved))
        equivalent["permission"][:2] = reversed(equivalent["permission"][:2])
        self.assertEqual(
            digest,
            COMPOSER.validate_hidden_native_agent(
                "summary", equivalent, tool_output
            ),
        )
        widened = json.loads(json.dumps(resolved))
        widened["permission"].insert(
            -1,
            {"permission": "read", "pattern": "README.md", "action": "allow"},
        )
        with self.assertRaisesRegex(
            COMPOSER.PermissionCompositionError, "terminally denied"
        ):
            COMPOSER.validate_hidden_native_agent("summary", widened, tool_output)

    def test_project_permission_overlay_is_preserved_without_loading_project_config(self) -> None:
        policy = COMPOSER.compose_policy(
            self.config,
            self.safe_config(),
            (
                {
                    "permission": {
                        "edit": "deny",
                        "bash": {"danger *": "deny", "safe *": "allow"},
                    },
                    "tools": {"webfetch": False, "future_tool": True},
                    "agent": {
                        "kokk": {
                            "permission": {
                                "task": "deny",
                                "read": {"secret/*": "deny"},
                            }
                        }
                    },
                },
            ),
        )

        self.assertEqual("deny", policy.agents["grillmester"]["edit"])
        self.assertEqual("deny", policy.agents["grillmester"]["webfetch"])
        self.assertEqual("ask", policy.agents["grillmester"]["future_tool"])
        self.assertEqual("deny", policy.agents["kokk"]["task"])
        self.assertEqual("deny", policy.agents["kokk"]["read"]["secret/*"])
        self.assertNotIn("safe *", policy.agents["kokk"]["bash"])

    def test_patterned_asks_downgrade_matching_generated_allows_without_weakening_denies(self) -> None:
        for task_pattern in ("k*", "*okk"):
            with self.subTest(task_pattern=task_pattern):
                policy = COMPOSER.compose_policy(
                    self.config,
                    self.safe_config(),
                    (
                        {
                            "permission": {
                                "task": {task_pattern: "ask"},
                                "skill": {"grillmester-*": "ask"},
                            }
                        },
                    ),
                )
                grillmester = COMPOSER._permission_rules(
                    policy.agents["grillmester"]
                )
                self.assertEqual(
                    "ask",
                    COMPOSER.evaluate_rules(grillmester, "task", "kokk"),
                )
                self.assertEqual(
                    "allow",
                    COMPOSER.evaluate_rules(
                        grillmester, "task", "grill-inspektor"
                    ),
                )
                self.assertEqual(
                    "deny",
                    COMPOSER.evaluate_rules(grillmester, "task", "killer"),
                )
                self.assertEqual(
                    "ask",
                    COMPOSER.evaluate_rules(
                        grillmester, "skill", "grillmester-review"
                    ),
                )

                researcher = COMPOSER._permission_rules(
                    policy.agents["researcher"]
                )
                self.assertEqual(
                    "deny",
                    COMPOSER.evaluate_rules(researcher, "task", "kokk"),
                )

    def test_wildcard_tool_ask_restricts_matching_exact_tool_allows(self) -> None:
        policy = COMPOSER.compose_policy(
            self.config,
            self.safe_config(),
            ({"permission": {"t*": {"k*": "ask"}}},),
        )
        rules = COMPOSER._permission_rules(policy.agents["grillmester"])

        self.assertEqual("ask", COMPOSER.evaluate_rules(rules, "task", "kokk"))
        self.assertEqual(
            "allow",
            COMPOSER.evaluate_rules(rules, "task", "grill-inspektor"),
        )
        self.assertEqual(
            "deny", COMPOSER.evaluate_rules(rules, "task", "killer")
        )
        kokk_rules = COMPOSER._permission_rules(policy.agents["kokk"])
        self.assertEqual(
            "deny", COMPOSER.evaluate_rules(kokk_rules, "task", "kokk")
        )

    def test_cross_tool_patterned_constraints_cover_researcher_exact_allows(self) -> None:
        for action in ("ask", "deny"):
            with self.subTest(action=action):
                policy = COMPOSER.compose_policy(
                    self.config,
                    self.safe_config(),
                    ({"permission": {"*": {"README*": action}}},),
                )
                rules = COMPOSER._permission_rules(policy.agents["researcher"])
                for tool in ("read", "glob", "grep", "list"):
                    with self.subTest(action=action, tool=tool):
                        self.assertEqual(
                            action,
                            COMPOSER.evaluate_rules(rules, tool, "README.md"),
                        )
                        self.assertEqual(
                            "allow",
                            COMPOSER.evaluate_rules(rules, tool, "src/main.py"),
                        )
                self.assertEqual(
                    "deny",
                    COMPOSER.evaluate_rules(rules, "task", "README.md"),
                )

    def test_overlapping_wildcard_denies_never_add_ask_fallbacks(self) -> None:
        policy = COMPOSER.compose_policy(
            self.config,
            self.safe_config(),
            (
                {
                    "permission": {
                        "*": {"secret": "deny"},
                        "t*": {"secret": "deny"},
                        "ta*": {"other": "deny"},
                    }
                },
            ),
        )
        rules = COMPOSER._permission_rules(policy.agents["grillmester"])

        self.assertEqual("deny", COMPOSER.evaluate_rules(rules, "task", "secret"))
        self.assertEqual("deny", COMPOSER.evaluate_rules(rules, "task", "other"))
        self.assertEqual("deny", COMPOSER.evaluate_rules(rules, "task", "unknown"))
        self.assertEqual(
            "deny", COMPOSER.evaluate_rules(rules, "todowrite", "secret")
        )
        self.assertEqual(
            "ask", COMPOSER.evaluate_rules(rules, "todowrite", "unknown")
        )
        kokk_rules = COMPOSER._permission_rules(policy.agents["kokk"])
        self.assertEqual(
            "deny", COMPOSER.evaluate_rules(kokk_rules, "task", "kokk")
        )

    def test_project_constraints_are_monotone_over_representative_tool_space(self) -> None:
        raw_constraints = {
            "*": {"README*": "ask", "secret*": "deny"},
            "t*": {"k*": "ask", "forbidden*": "deny"},
            "skill": {"grillmester-*": "ask"},
            "external_directory": {
                "/private/*": "ask",
                "/secrets/*": "deny",
            },
        }
        baseline = COMPOSER.compose_policy(self.config, self.safe_config())
        restricted = COMPOSER.compose_policy(
            self.config,
            self.safe_config(),
            ({"permission": raw_constraints},),
        )
        samples = {
            "read": ("README.md", "secret.env", "src/main.py"),
            "glob": ("README.md", "secret.txt", "src/*.py"),
            "grep": ("README", "secret-token", "needle"),
            "list": ("README", "secret-dir", "src"),
            "task": ("kokk", "killer", "forbidden-agent", "researcher"),
            "skill": (
                "grillmester-review",
                "grillmester-doctor",
                "ambient-skill",
            ),
            "external_directory": (
                "/private/cache",
                "/secrets/token",
                "/tmp/public",
            ),
            "question": ("README question", "ordinary question"),
            "future_tool": ("README", "secret-value", "ordinary"),
        }
        constraints = tuple(
            (tool_pattern, resource_pattern, action)
            for tool_pattern, resources in raw_constraints.items()
            for resource_pattern, action in resources.items()
        )
        severity = {"allow": 0, "ask": 1, "deny": 2}

        for agent_id in baseline.agents:
            baseline_rules = COMPOSER._permission_rules(
                baseline.agents[agent_id]
            )
            restricted_rules = COMPOSER._permission_rules(
                restricted.agents[agent_id]
            )
            for tool, resources in samples.items():
                for resource in resources:
                    with self.subTest(
                        agent=agent_id, tool=tool, resource=resource
                    ):
                        before = COMPOSER.evaluate_rules(
                            baseline_rules, tool, resource
                        )
                        after = COMPOSER.evaluate_rules(
                            restricted_rules, tool, resource
                        )
                        self.assertGreaterEqual(severity[after], severity[before])
                        for tool_pattern, resource_pattern, action in constraints:
                            if not (
                                COMPOSER.wildcard_match(tool, tool_pattern)
                                and COMPOSER.wildcard_match(
                                    resource, resource_pattern
                                )
                            ):
                                continue
                            if action == "deny":
                                self.assertEqual("deny", after)
                            elif before == "allow":
                                self.assertNotEqual("allow", after)

    def test_only_fingerprinted_project_instruction_chain_is_accepted(self) -> None:
        instruction = str((self.root / "consumer/AGENTS.md").resolve())
        policy = COMPOSER.compose_policy(
            self.config,
            self.safe_config(),
            (),
            (instruction,),
        )
        self.assertEqual(
            [instruction], json.loads(policy.config_content)["instructions"]
        )
        COMPOSER.require_no_external_extensions(
            self.safe_config(instructions=[instruction]),
            (instruction,),
        )
        with self.assertRaisesRegex(
            COMPOSER.PermissionCompositionError, "fingerprinted project"
        ):
            COMPOSER.require_no_external_extensions(
                self.safe_config(
                    instructions=[instruction, "https://evil.invalid/prompt"]
                ),
                (instruction,),
            )

    def test_wildcard_match_mirrors_optional_trailing_arguments(self) -> None:
        self.assertTrue(COMPOSER.wildcard_match("git", "git *"))
        self.assertTrue(COMPOSER.wildcard_match("git status", "git *"))
        self.assertFalse(COMPOSER.wildcard_match("github", "git *"))
        self.assertTrue(COMPOSER.wildcard_match("file1.txt", "file?.txt"))
        self.assertFalse(COMPOSER.wildcard_match("file12.txt", "file?.txt"))

    def test_duplicate_or_malformed_debug_json_fails_closed(self) -> None:
        with self.assertRaisesRegex(
            COMPOSER.PermissionCompositionError, "duplicate JSON key"
        ):
            COMPOSER.parse_resolved_config('{"permission":{},"permission":{}}')
        with self.assertRaisesRegex(
            COMPOSER.PermissionCompositionError, "must be an object"
        ):
            COMPOSER.parse_resolved_config("[]")

    def test_skill_origin_validation_rejects_shadowing(self) -> None:
        skills = [
            {
                "name": COMPOSER.PINNED_BUILTIN_SKILL_ID,
                "description": "Pinned built-in",
                "location": COMPOSER.PINNED_BUILTIN_SKILL_LOCATION,
                "content": "Pinned built-in content\n",
            }
        ]
        for path in sorted((self.config / "skills").iterdir()):
            if not path.is_dir():
                continue
            skill_path = path / "SKILL.md"
            fields, _body = COMPOSER._parse_frontmatter_document(skill_path)
            text = skill_path.read_text(encoding="utf-8")
            end = text.find("\n---\n", 4)
            projected_content = (
                text[: end + len("\n---\n")]
                + f"{COMPOSER.OPENCODE_SKILL_PROBE_MARKER} for {path.name}.\n"
            )
            skill_path.write_text(projected_content, encoding="utf-8")
            skills.append(
                {
                    "name": path.name,
                    "description": fields["description"],
                    "location": str(skill_path),
                    "content": (
                        f"{COMPOSER.OPENCODE_SKILL_PROBE_MARKER} for {path.name}.\n"
                    ),
                }
            )
        digest = COMPOSER.validate_skill_origins(skills, self.config)
        self.assertRegex(digest, r"^[0-9a-f]{64}$")
        self.assertEqual(
            digest,
            COMPOSER.validate_skill_origins(list(reversed(skills)), self.config),
        )
        skills[1]["location"] = str(self.root / "shadow/SKILL.md")
        with self.assertRaisesRegex(
            COMPOSER.PermissionCompositionError, "unreadable origin|shadowed"
        ):
            COMPOSER.validate_skill_origins(skills, self.config)

        fields = ("description", "content")
        for field in fields:
            changed = json.loads(json.dumps(skills))
            changed[1]["location"] = str(
                self.config / "skills" / changed[1]["name"] / "SKILL.md"
            )
            changed[1][field] = "changed"
            with self.subTest(field=field), self.assertRaisesRegex(
                COMPOSER.PermissionCompositionError, f"changed.*{field}"
            ):
                COMPOSER.validate_skill_origins(changed, self.config)

        wrong_builtin = json.loads(json.dumps(skills))
        wrong_builtin[0]["location"] = "/tmp/not-built-in"
        wrong_builtin[1]["location"] = str(
            self.config / "skills" / wrong_builtin[1]["name"] / "SKILL.md"
        )
        with self.assertRaisesRegex(
            COMPOSER.PermissionCompositionError, "built-in skill changed"
        ):
            COMPOSER.validate_skill_origins(wrong_builtin, self.config)

        unexpected = json.loads(json.dumps(skills))
        unexpected[1]["location"] = str(
            self.config / "skills" / unexpected[1]["name"] / "SKILL.md"
        )
        unexpected.append(
            {
                "name": "ambient",
                "description": "ambient",
                "location": "/tmp/ambient/SKILL.md",
                "content": "ambient\n",
            }
        )
        with self.assertRaisesRegex(
            COMPOSER.PermissionCompositionError, "unexpected skill"
        ):
            COMPOSER.validate_skill_origins(unexpected, self.config)


if __name__ == "__main__":
    unittest.main()
