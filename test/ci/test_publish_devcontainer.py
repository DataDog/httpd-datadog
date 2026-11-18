import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


PUBLISHER = Path(__file__).resolve().parents[2] / ".gitlab/publish-devcontainer.sh"
SOURCE_IMAGE = "registry.ddbuild.io/ci/httpd-datadog/devcontainer:amd64-abc123"


class PublishDevcontainerTest(unittest.TestCase):
    def run_publisher(self, overrides=None):
        with tempfile.TemporaryDirectory() as directory:
            command_log = Path(directory) / "commands.jsonl"
            mock = Path(directory) / "dd-pkg"
            mock.write_text(
                f"#!{sys.executable}\n"
                "import json, os, sys\n"
                "with open(os.environ['COMMAND_LOG'], 'a') as output:\n"
                "    output.write(json.dumps(sys.argv[1:]) + '\\n')\n"
                "if os.environ.get('FAIL_PUBLISH') and '--sources' in sys.argv:\n"
                "    sys.exit(1)\n"
            )
            mock.chmod(0o755)
            curl = Path(directory) / "curl"
            curl.write_text('#!/bin/sh\nprintf "%s" "$CACHE_STATUS"\n')
            curl.chmod(0o755)
            environment = {
                **os.environ,
                "PATH": f"{directory}:{os.environ['PATH']}",
                "COMMAND_LOG": str(command_log),
                "DEVCONTAINER_IMAGE_AMD64": SOURCE_IMAGE,
                "DEVCONTAINER_IMAGE_AMD64_CI": SOURCE_IMAGE + "-ci",
                "CI_IMAGE_HASH": "abc123",
                "DEVCONTAINER_PUBLIC_IMAGE": "httpd-datadog-ci-dev",
                "FAIL_PUBLISH": "",
                "CACHE_STATUS": "404",
                **(overrides or {}),
            }
            result = subprocess.run(
                ["sh", str(PUBLISHER)], env=environment, capture_output=True, text=True
            )
            commands = (
                [json.loads(line) for line in command_log.read_text().splitlines()]
                if command_log.exists() else []
            )
            return result, commands

    def test_publishes_plain_image_before_advancing_main(self):
        result, commands = self.run_publisher()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(commands), 2)
        publish, promote = commands
        self.assertEqual(publish[publish.index("--sources") + 1], SOURCE_IMAGE)
        self.assertEqual(
            publish[publish.index("--destinations") + 1], "httpd-datadog-ci-dev:abc123"
        )
        self.assertEqual(
            promote[promote.index("--tag-reference") + 1], "httpd-datadog-ci-dev:abc123"
        )
        self.assertEqual(promote[promote.index("--new-tags") + 1], "main")
        for command in commands:
            self.assertEqual(command[command.index("--registries") + 1], "dev")
            self.assertIn("--signing=false", command)

    def test_failed_publication_does_not_advance_main(self):
        result, commands = self.run_publisher({"FAIL_PUBLISH": "1"})
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(commands), 1)
        self.assertNotIn("--new-tags", commands[0])

    def test_cached_image_is_only_retagged(self):
        result, commands = self.run_publisher({"CACHE_STATUS": "200"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(commands), 1)
        self.assertIn("--tag-reference", commands[0])
        self.assertNotIn("--sources", commands[0])

    def test_registry_errors_do_not_publish_or_advance_main(self):
        for status in ("403", "500"):
            with self.subTest(status=status):
                result, commands = self.run_publisher({"CACHE_STATUS": status})
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(commands, [])

    def test_missing_inputs_do_not_publish(self):
        for variable in (
            "DEVCONTAINER_IMAGE_AMD64", "CI_IMAGE_HASH", "DEVCONTAINER_PUBLIC_IMAGE"
        ):
            with self.subTest(variable=variable):
                result, commands = self.run_publisher({variable: ""})
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(commands, [])
