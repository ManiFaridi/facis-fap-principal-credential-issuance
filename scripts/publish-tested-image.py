#!/usr/bin/env python3
# Copyright (c) 2026 LEANEA GmbH and others.
# SPDX-License-Identifier: Apache-2.0
"""Publish the exact tested archive; refuse to replace an existing different tag."""

import argparse
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

OFFICIAL = "eclipse-xfsc/facis-fap-principal-credential-issuance"


def command(args, cwd):
    result = subprocess.run(args, cwd=cwd, text=True, capture_output=True, timeout=1200)
    if result.returncode:
        raise RuntimeError("Command failed: " + args[0] + " " + " ".join(args[1:3]))
    return result.stdout.strip()


def tag_exists(repository, tag):
    # These release repositories must be publicly visible before publication.
    # A hidden/private repository must never be mistaken for an absent tag.
    with urlopen(f"https://hub.docker.com/v2/repositories/{repository}/", timeout=30) as response:
        information = json.load(response)
    if information.get("is_private") is not False:
        raise ValueError("The release repository must be verified as public by its owner.")
    try:
        with urlopen(f"https://hub.docker.com/v2/repositories/{repository}/tags/{tag}/", timeout=30) as response:
            return response.status == 200
    except HTTPError as error:
        if error.code == 404:
            return False
        raise


def publish(kind, root, env, run=command, exists=tag_exists):
    root = Path(root)
    if env.get("GITHUB_REPOSITORY") != OFFICIAL:
        raise ValueError("Publication is restricted to the official source repository.")
    if env.get("GITHUB_EVENT_NAME") not in ("push", "workflow_dispatch"):
        raise ValueError("Pull requests cannot publish images.")
    version = (root / "VERSION").read_text().strip()
    sha = env.get("GITHUB_SHA", "")
    if not re.fullmatch(r"[0-9a-f]{40}", sha) or run(["git", "rev-parse", "HEAD"], root) != sha:
        raise ValueError("The checked-out source does not match the workflow commit.")
    ref = env.get("GITHUB_REF", "")
    if ref == "refs/heads/main" and env.get("GITHUB_EVENT_NAME") == "push":
        tag = "sha-" + sha
    elif ref == "refs/tags/v" + version:
        tag = "v" + version
    else:
        raise ValueError("Publication requires main or the exact release-version tag.")
    if kind not in ("application", "participant"):
        raise ValueError("Unknown image kind.")
    namespace = env.get("DOCKERHUB_NAMESPACE", "ecofacis")
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", namespace):
        raise ValueError("Invalid Docker Hub namespace.")
    image = "fap-pci" if kind == "application" else "fap-pci-participant"
    local = image + ":ci"
    archive = root / (kind + "-image.tar.gz")
    checksum = archive.with_name(archive.name + ".sha256").read_text().split()
    if len(checksum) != 2 or checksum[1] != archive.name:
        raise ValueError("Unexpected image archive checksum entry.")
    with archive.open("rb") as source:
        actual = hashlib.file_digest(source, "sha256").hexdigest()
    if checksum[0] != actual:
        raise ValueError("The tested image archive failed checksum verification.")
    metadata = json.loads((root / ("image-" + kind + ".json")).read_text())[0]
    run(["docker", "load", "--input", str(archive)], root)
    loaded = json.loads(run(["docker", "image", "inspect", local], root))[0]
    if loaded["Id"] != metadata["Id"]:
        raise ValueError("The loaded image differs from the tested image.")
    labels = loaded.get("Config", {}).get("Labels") or {}
    if labels.get("org.opencontainers.image.revision") != sha or labels.get("org.opencontainers.image.version") != version:
        raise ValueError("Image source/version labels do not match the checked-out revision.")
    evidence_files = ["image-" + kind + ".json", "sbom-" + kind + ".cdx.json"]
    evidence_files += ["scan-base.json", "scan-application.json", "startup-check.log"] if kind == "application" else ["scan-participant.json"]
    evidence = {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in evidence_files}
    repository = namespace + "/" + image
    target = repository + ":" + tag
    already = exists(repository, tag)
    if already:
        remote = json.loads(run(["docker", "buildx", "imagetools", "inspect", target, "--raw"], root))
        if remote.get("config", {}).get("digest") != loaded["Id"]:
            raise ValueError("The existing registry tag names a different image; it was not overwritten.")
    else:
        run(["docker", "tag", local, target], root)
        run(["docker", "push", target], root)
    digest = run(["docker", "buildx", "imagetools", "inspect", target, "--format", "{{.Manifest.Digest}}"], root).strip('"')
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        raise ValueError("The registry did not return a valid immutable image digest.")
    return {
        "kind": kind, "sourceRepository": OFFICIAL, "sourceCommit": sha,
        "version": version, "tag": tag, "image": repository + "@" + digest,
        "digest": digest, "imageId": loaded["Id"], "alreadyPublished": already,
        "archiveSha256": actual, "evidenceSha256": evidence,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=["application", "participant"])
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    receipt = publish(args.kind, Path.cwd(), os.environ)
    args.out.write_text(json.dumps(receipt, indent=2) + "\n")
    print("Verified published image:", receipt["image"])


if __name__ == "__main__":
    main()
