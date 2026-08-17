from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "verify_wheelhouse.py"


def _write_manifest(path: Path, filename: str, digest: str) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "files": [
                    {
                        "filename": filename,
                        "sha256": digest,
                        "source": "https://pypi.org/project/example/",
                        "license": "MIT",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def test_artifact_mode_accepts_matching_hash(tmp_path: Path) -> None:
    wheelhouse = tmp_path / "wheelhouse"
    wheelhouse.mkdir()
    artifact = wheelhouse / "example-1.0-py3-none-any.whl"
    artifact.write_bytes(b"approved-wheel")
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    manifest = tmp_path / "manifest.json"
    _write_manifest(manifest, artifact.name, digest)

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--manifest",
            str(manifest),
            "--wheelhouse",
            str(wheelhouse),
            "--mode",
            "artifacts",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr


def test_artifact_mode_rejects_hash_mismatch(tmp_path: Path) -> None:
    wheelhouse = tmp_path / "wheelhouse"
    wheelhouse.mkdir()
    artifact = wheelhouse / "example-1.0-py3-none-any.whl"
    artifact.write_bytes(b"tampered-wheel")
    manifest = tmp_path / "manifest.json"
    _write_manifest(manifest, artifact.name, "0" * 64)

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--manifest",
            str(manifest),
            "--wheelhouse",
            str(wheelhouse),
            "--mode",
            "artifacts",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert "hash_mismatch" in completed.stderr


def test_complete_mode_accepts_locked_wheel_without_provenance_entry(tmp_path: Path) -> None:
    wheelhouse = tmp_path / "wheelhouse"
    wheelhouse.mkdir()
    native = wheelhouse / "native-1.0-py3-none-any.whl"
    dependency = wheelhouse / "dependency-1.0-py3-none-any.whl"
    native.write_bytes(b"approved-native")
    dependency.write_bytes(b"locked-dependency")
    native_hash = hashlib.sha256(native.read_bytes()).hexdigest()
    dependency_hash = hashlib.sha256(dependency.read_bytes()).hexdigest()
    manifest = tmp_path / "manifest.json"
    _write_manifest(manifest, native.name, native_hash)
    lock = tmp_path / "requirements.lock"
    lock.write_text(
        f"native==1.0 --hash=sha256:{native_hash}\n"
        f"dependency==1.0 --hash=sha256:{dependency_hash}\n",
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--manifest",
            str(manifest),
            "--wheelhouse",
            str(wheelhouse),
            "--requirements",
            str(lock),
            "--mode",
            "complete",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr


def test_complete_mode_rejects_wheel_missing_from_lock(tmp_path: Path) -> None:
    wheelhouse = tmp_path / "wheelhouse"
    wheelhouse.mkdir()
    native = wheelhouse / "native-1.0-py3-none-any.whl"
    extra = wheelhouse / "extra-1.0-py3-none-any.whl"
    native.write_bytes(b"approved-native")
    extra.write_bytes(b"not-locked")
    native_hash = hashlib.sha256(native.read_bytes()).hexdigest()
    manifest = tmp_path / "manifest.json"
    _write_manifest(manifest, native.name, native_hash)
    lock = tmp_path / "requirements.lock"
    lock.write_text(f"native==1.0 --hash=sha256:{native_hash}\n", encoding="utf-8")

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--manifest",
            str(manifest),
            "--wheelhouse",
            str(wheelhouse),
            "--requirements",
            str(lock),
            "--mode",
            "complete",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert "lock_hash_missing" in completed.stderr


def test_complete_mode_rejects_locked_bytes_renamed_as_another_package(tmp_path: Path) -> None:
    wheelhouse = tmp_path / "wheelhouse"
    wheelhouse.mkdir()
    native = wheelhouse / "native-1.0-py3-none-any.whl"
    renamed = wheelhouse / "renamed-1.0-py3-none-any.whl"
    native.write_bytes(b"approved-native")
    renamed.write_bytes(native.read_bytes())
    native_hash = hashlib.sha256(native.read_bytes()).hexdigest()
    manifest = tmp_path / "manifest.json"
    _write_manifest(manifest, native.name, native_hash)
    lock = tmp_path / "requirements.lock"
    lock.write_text(f"native==1.0 --hash=sha256:{native_hash}\n", encoding="utf-8")

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--manifest",
            str(manifest),
            "--wheelhouse",
            str(wheelhouse),
            "--requirements",
            str(lock),
            "--mode",
            "complete",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert "lock_hash_missing:renamed" in completed.stderr
