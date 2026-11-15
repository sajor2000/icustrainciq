#!/usr/bin/env python3
"""Create a local, code-only Lookahead deployment archive; never upload it.

Only the source/configuration paths below are eligible. Roster, context, scores,
weights, data, credentials and environment directories are outside the allowlist.
"""

import argparse
import gzip
import hashlib
import io
import json
import os
import pathlib
import tarfile
import tempfile

TREE_ALLOWLIST = {
    "app": {".py", ".html", ".css", ".js"},
    "icutwin": {".py", ".yaml", ".yml", ".html"},
    "examples": {".yaml", ".yml"},
}
FILE_ALLOWLIST = (
    "pyproject.toml",
    "uv.lock",
    "README.md",
    "AGENTS.md",
    "fuzzball/t7-lookahead-chat.fz",
    "fuzzball/t7-lookahead-prepare.fz",
    "fuzzball/t7-lookahead-forecast.fz",
    "docs/LOOKAHEAD_DEMO.md",
    "docs/CLAUDE_WORKFLOW_ALIGNMENT.md",
    "docs/COMPUTE_PLAN.md",
    "scripts/package_lookahead_demo.py",
    "scripts/prepare_lookahead_cohort.py",
    "scripts/run_cohort.py",
    "requirements/t7-model.in",
    "requirements/t7-model.txt",
)
REQUIRED = (
    "app/board.py",
    "app/chat_agent.py",
    "app/dispatcher.py",
    "app/demo_context.py",
    "app/evidence.py",
    "app/aggregate.py",
    "app/rooms.py",
    "app/clif_now.py",
    "app/ward_check.py",
    "app/fake_names.py",
    "app/static/index.html",
    "icutwin/scoring/extractor.py",
    "icutwin/scoring/rep_based.py",
    "icutwin/scoring/winnower.py",
    "scripts/run_cohort.py",
    "requirements/t7-model.in",
    "requirements/t7-model.txt",
    "uv.lock",
    "fuzzball/t7-lookahead-prepare.fz",
    "fuzzball/t7-lookahead-chat.fz",
    "fuzzball/t7-lookahead-forecast.fz",
    "docs/LOOKAHEAD_DEMO.md",
    "docs/CLAUDE_WORKFLOW_ALIGNMENT.md",
)
EXCLUDED_PARTS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    "credentials",
    "secrets",
    "private",
    "data",
    "datasets",
    "results",
    "models",
}


def _reject_symlinks(root: pathlib.Path, relative: pathlib.Path) -> None:
    path = root
    for part in relative.parts:
        path = path / part
        if path.is_symlink():
            raise ValueError("source allowlist contains a symlink")


def source_files(root: pathlib.Path) -> list[pathlib.Path]:
    """Return eligible regular files, failing closed for eligible symlinks."""
    chosen = set()
    for folder, suffixes in TREE_ALLOWLIST.items():
        _reject_symlinks(root, pathlib.Path(folder))
        for path in (root / folder).rglob("*"):
            rel = path.relative_to(root)
            if any(part.lower() in EXCLUDED_PARTS for part in rel.parts):
                continue
            _reject_symlinks(root, rel)
            if path.is_file() and path.suffix.lower() in suffixes:
                if any(word in path.stem.lower() for word in ("secret", "credential")):
                    continue
                chosen.add(rel)
    for name in FILE_ALLOWLIST:
        path = root / name
        _reject_symlinks(root, pathlib.Path(name))
        if path.is_file():
            chosen.add(pathlib.Path(name))
    missing = [name for name in REQUIRED if pathlib.Path(name) not in chosen]
    if missing:
        raise ValueError("required deployment source is missing: " + ", ".join(missing))
    return sorted(chosen)


def package(
    root: pathlib.Path, output: pathlib.Path, frontend_file: pathlib.Path | None = None
) -> dict:
    root, output = root.resolve(), output.expanduser().absolute()
    # This command promises a local handoff, so reject common synced destinations.
    destination = output.parent.resolve() / output.name
    if any(
        part.lower() in {"dropbox", "cloudstorage", "mobile documents"}
        for part in destination.parts
    ):
        raise ValueError("choose a local, unsynced output directory")
    if destination.is_relative_to(root):
        raise ValueError("write the archive outside the source checkout")
    if destination.exists() or destination.is_symlink():
        raise ValueError("output already exists; choose a new archive name")
    paths = source_files(root)
    payloads = [(rel.as_posix(), (root / rel).read_bytes()) for rel in paths]
    frontend_name = "app/static/index.html"
    frontend_source = "repository"
    if frontend_file is not None:
        frontend_file = frontend_file.expanduser().absolute()
        _reject_symlinks(
            pathlib.Path(frontend_file.anchor),
            frontend_file.relative_to(frontend_file.anchor),
        )
        # macOS temporary directories live below the system /private prefix.
        source_parts = frontend_file.parts
        if source_parts[:2] == ("/", "private"):
            source_parts = source_parts[2:]
        if (
            frontend_file.suffix.lower() != ".html"
            or any(part.lower() in EXCLUDED_PARTS for part in source_parts)
            or not frontend_file.is_file()
        ):
            raise ValueError(
                "frontend must be an HTML source file outside data directories"
            )
        frontend_data = frontend_file.read_bytes()
        payloads = [
            (name, frontend_data if name == "app/static/index.html" else data)
            for name, data in payloads
        ]
        frontend_name, frontend_source = frontend_file.name, "explicit-html"
    frontend_data = dict(payloads)["app/static/index.html"]
    manifest = {
        "schema_version": 1,
        "kind": "lookahead-code-only",
        "frontend": {
            "source": frontend_source,
            "source_name": frontend_name,
            "sha256": hashlib.sha256(frontend_data).hexdigest(),
            "bytes": len(frontend_data),
        },
        "files": [
            {
                "path": name,
                "bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
            for name, data in payloads
        ],
    }
    payloads.append(("LOOKAHEAD_PACKAGE.json", json.dumps(manifest, indent=2).encode()))
    destination.parent.mkdir(parents=True, exist_ok=True)
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as raw:
            tmp = pathlib.Path(raw.name)
            with gzip.GzipFile(fileobj=raw, mode="wb", filename="", mtime=0) as gz:
                with tarfile.open(fileobj=gz, mode="w") as archive:
                    for name, data in payloads:
                        info = tarfile.TarInfo("code/" + name)
                        info.size, info.mode, info.mtime = len(data), 0o644, 0
                        archive.addfile(info, io.BytesIO(data))
            raw.flush()
            os.fsync(raw.fileno())
        # Atomic, no-clobber publication: an existing archive is never replaced.
        os.link(tmp, destination)
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)
    return {"archive": str(destination), "files": len(paths), "code_only": True}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[1]
    )
    parser.add_argument("--out", required=True, type=pathlib.Path)
    parser.add_argument(
        "--frontend-file",
        type=pathlib.Path,
        help="stage an exact approved HTML source snapshot as app/static/index.html",
    )
    args = parser.parse_args()
    try:
        result = package(args.root, args.out, args.frontend_file)
    except (OSError, ValueError) as exc:
        raise SystemExit(str(exc)) from None
    print(json.dumps(result))


if __name__ == "__main__":
    main()
