"""Offline wheelhouse integrity verifier."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import TypedDict, cast


class ManifestEntry(TypedDict):
    filename: str
    sha256: str
    source: str
    license: str


LOCKED_REQUIREMENT = re.compile(r"^([A-Za-z0-9_.-]+)==([^\s\\;]+)")
LOCKED_HASH = re.compile(r"sha256:([0-9a-f]{64})")


def _normalize_distribution(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _wheel_identity(path: Path) -> tuple[str, str]:
    parts = path.name.removesuffix(".whl").split("-")
    if len(parts) < 5:
        raise ValueError(f"invalid_wheel_filename:{path.name}")
    return _normalize_distribution(parts[0]), parts[1]


def _locked_artifacts(lock_text: str) -> dict[tuple[str, str], set[str]]:
    artifacts: dict[tuple[str, str], set[str]] = {}
    current: tuple[str, str] | None = None
    for line in lock_text.splitlines():
        if match := LOCKED_REQUIREMENT.match(line):
            current = (_normalize_distribution(match.group(1)), match.group(2))
            artifacts.setdefault(current, set())
        if current is not None:
            artifacts[current].update(LOCKED_HASH.findall(line))
    return artifacts


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_manifest(path: Path) -> tuple[ManifestEntry, ...]:
    payload = cast(object, json.loads(path.read_text(encoding="utf-8")))
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ValueError("invalid_manifest_schema")
    files = payload.get("files")
    if not isinstance(files, list):
        raise TypeError("invalid_manifest_schema")

    entries: list[ManifestEntry] = []
    seen: set[str] = set()
    for raw in files:
        if not isinstance(raw, dict):
            raise TypeError("invalid_manifest_entry")
        values = {name: raw.get(name) for name in ("filename", "sha256", "source", "license")}
        if not all(isinstance(value, str) and value for value in values.values()):
            raise ValueError("invalid_manifest_entry")
        entry = cast(ManifestEntry, values)
        filename = entry["filename"]
        if Path(filename).name != filename or filename in seen:
            raise ValueError("invalid_manifest_filename")
        if re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]) is None:
            raise ValueError("invalid_manifest_hash")
        seen.add(filename)
        entries.append(entry)
    return tuple(entries)


def verify(
    manifest_path: Path,
    wheelhouse: Path,
    mode: str,
    requirements_path: Path | None,
) -> None:
    if mode not in {"artifacts", "complete"}:
        raise ValueError("invalid_mode")
    entries = _load_manifest(manifest_path)
    for entry in entries:
        artifact = wheelhouse / entry["filename"]
        if not artifact.is_file():
            raise ValueError(f"missing_artifact:{entry['filename']}")
        if _sha256(artifact) != entry["sha256"]:
            raise ValueError(f"hash_mismatch:{entry['filename']}")

    if mode == "complete":
        if requirements_path is None:
            raise ValueError("requirements_required")
        lock_text = requirements_path.read_text(encoding="utf-8")
        locked_artifacts = _locked_artifacts(lock_text)
        wheel_paths = tuple(path for path in wheelhouse.glob("*.whl") if path.is_file())
        wheel_identities = {_wheel_identity(path) for path in wheel_paths}
        for path in wheel_paths:
            identity = _wheel_identity(path)
            if _sha256(path) not in locked_artifacts.get(identity, set()):
                raise ValueError(f"lock_hash_missing:{path.name}")
        missing = set(locked_artifacts) - wheel_identities
        if missing:
            name, version = min(missing)
            raise ValueError(f"wheel_missing:{name}=={version}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--wheelhouse", type=Path, required=True)
    parser.add_argument("--requirements", type=Path)
    parser.add_argument("--mode", choices=("artifacts", "complete"), required=True)
    args = parser.parse_args()
    try:
        verify(args.manifest, args.wheelhouse, args.mode, args.requirements)
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        print(str(error), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
