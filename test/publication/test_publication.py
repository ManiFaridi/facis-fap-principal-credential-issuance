# Copyright (c) 2026 LEANEA GmbH and others.
# SPDX-License-Identifier: Apache-2.0
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("publisher", ROOT / "scripts/publish-tested-image.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "VERSION").write_text("0.5.0-rc.16\n")
        self.sha = "a" * 40
        self.image_id = "sha256:" + "b" * 64
        self.digest = "sha256:" + "c" * 64
        self.env = {
            "GITHUB_REPOSITORY": MODULE.OFFICIAL,
            "GITHUB_EVENT_NAME": "push", "GITHUB_SHA": self.sha,
            "GITHUB_REF": "refs/tags/v0.5.0-rc.16",
        }
        self.metadata = {"Id": self.image_id, "Config": {"Labels": {
            "org.opencontainers.image.revision": self.sha,
            "org.opencontainers.image.version": "0.5.0-rc.16",
        }}}
        (self.root / "image-application.json").write_text(json.dumps([self.metadata]))
        for name in ["sbom-application.cdx.json", "scan-base.json", "scan-application.json", "startup-check.log"]:
            (self.root / name).write_text("synthetic evidence fixture\n")
        archive = self.root / "application-image.tar.gz"
        archive.write_bytes(b"synthetic Docker archive fixture")
        checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
        archive.with_name(archive.name + ".sha256").write_text(checksum + "  " + archive.name + "\n")
        self.calls = []
        self.remote_id = self.image_id

    def run_command(self, args, cwd):
        self.calls.append(args)
        if args[:2] == ["git", "rev-parse"]:
            return self.sha
        if args[:3] == ["docker", "image", "inspect"]:
            return json.dumps([self.metadata])
        if args[-1] == "--raw":
            return json.dumps({"config": {"digest": self.remote_id}})
        if "--format" in args:
            return self.digest
        return ""

    def publish(self, exists=False):
        return MODULE.publish("application", self.root, self.env, self.run_command, lambda *_: exists)

    def pushed(self):
        return any(c[:2] == ["docker", "push"] for c in self.calls)

    def test_pull_request_cannot_publish(self):
        self.env["GITHUB_EVENT_NAME"] = "pull_request"
        with self.assertRaises(ValueError):
            self.publish()
        self.assertEqual(self.calls, [])

    def test_fork_cannot_publish(self):
        self.env["GITHUB_REPOSITORY"] = "example/fork"
        with self.assertRaises(ValueError):
            self.publish()
        self.assertEqual(self.calls, [])

    def test_wrong_release_tag_cannot_publish(self):
        self.env["GITHUB_REF"] = "refs/tags/v0.5.0-rc.15"
        with self.assertRaises(ValueError):
            self.publish()
        self.assertFalse(self.pushed())

    def test_corrupted_archive_cannot_publish(self):
        (self.root / "application-image.tar.gz").write_bytes(b"corrupted")
        with self.assertRaises(ValueError):
            self.publish()
        self.assertFalse(self.pushed())

    def test_new_publication_records_the_registry_digest(self):
        result = self.publish()
        self.assertTrue(self.pushed())
        self.assertEqual(result["image"], "ecofacis/fap-pci@" + self.digest)
        self.assertEqual(result["sourceCommit"], self.sha)

    def test_identical_existing_tag_does_not_push_again(self):
        result = self.publish(True)
        self.assertFalse(self.pushed())
        self.assertTrue(result["alreadyPublished"])

    def test_different_existing_tag_is_never_replaced(self):
        self.remote_id = "sha256:" + "d" * 64
        with self.assertRaises(ValueError):
            self.publish(True)
        self.assertFalse(self.pushed())

    def test_wrong_image_provenance_cannot_publish(self):
        self.metadata["Config"]["Labels"]["org.opencontainers.image.revision"] = "e" * 40
        with self.assertRaises(ValueError):
            self.publish()
        self.assertFalse(self.pushed())

    def test_missing_sbom_cannot_publish(self):
        (self.root / "sbom-application.cdx.json").unlink()
        with self.assertRaises(FileNotFoundError):
            self.publish()
        self.assertFalse(self.pushed())


if __name__ == "__main__":
    unittest.main()
