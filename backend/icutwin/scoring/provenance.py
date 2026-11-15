"""which weights made a file (stdlib only, so the GPU extract job can import it
without the probe stack): the digest of a model folder, and the note icutwin-extract
leaves beside each features file"""

import hashlib
import json
import pathlib


def weights_digest(model_home) -> str | None:
    """sha256 over the model's weight files (and config.json): ties probes, features
    and scores to the weights, not to a folder name. None when no weights are found."""
    home = pathlib.Path(model_home).expanduser()
    files = sorted(home.glob("*.safetensors")) or sorted(
        home.glob("pytorch_model*.bin")
    )
    if not files:
        return None
    h = hashlib.sha256()
    for f in [
        *files,
        *([home / "config.json"] if (home / "config.json").is_file() else []),
    ]:
        h.update(f.name.encode())
        with f.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
    return h.hexdigest()


def features_meta_path(features: pathlib.Path) -> pathlib.Path:
    return pathlib.Path(features).with_suffix(".meta.json")


def features_digest(features: pathlib.Path) -> str | None:
    """the weights digest recorded beside a features file; None when there is none"""
    try:
        got = json.loads(features_meta_path(features).read_text())
        return got.get("weights_sha256") if isinstance(got, dict) else None
    except (OSError, ValueError):
        return None


def write_features_meta(features: pathlib.Path, model_home) -> None:
    """provenance beside a features file: which weights extracted it
    (icutwin-extract writes it; the scorers refuse a file without it)"""
    features_meta_path(features).write_text(
        json.dumps(
            {
                "model": pathlib.Path(model_home).name,
                "weights_sha256": weights_digest(model_home),
            }
        )
    )
