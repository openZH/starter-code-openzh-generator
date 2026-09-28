"""Publication gate contracts from README: integrity, completeness and offline CLI."""

import hashlib
import json
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from starter_code_openzh_updater import updater


@pytest.mark.parametrize("artifact", ["index", "python", "r"])
@pytest.mark.parametrize("damage", ["missing", "modified"])
def test_verification_rejects_damaged_artifacts(
    generated_release: updater.Config, artifact: str, damage: str
) -> None:
    """Both absent files and changed bytes must block publication."""
    config = generated_release
    manifest = json.loads((config.temp_prefix / "manifest.json").read_text())
    paths = {
        "index": "index.md",
        "python": manifest["resource_files"][0]["python"],
        "r": manifest["resource_files"][0]["r"],
    }
    path = config.temp_prefix / paths[artifact]
    if damage == "missing":
        path.unlink()
    else:
        path.write_bytes(path.read_bytes() + b"\nchanged\n")
    with pytest.raises(ValueError, match="integrity"):
        updater.verify_output(config)


@pytest.mark.parametrize("field", ["resources", "datasets", "resource_files", "files"])
def test_verification_rejects_inconsistent_manifest(
    generated_release: updater.Config, field: str
) -> None:
    """A manifest cannot silently omit a resource or misreport release counts."""
    config = generated_release
    path = config.temp_prefix / "manifest.json"
    manifest = json.loads(path.read_text())
    if field in {"resources", "datasets"}:
        manifest[field] += 1
    elif field == "resource_files":
        manifest[field][1] = manifest[field][0].copy()
    else:
        del manifest[field]["index.md"]
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="integrity"):
        updater.verify_output(config)


@pytest.mark.parametrize("directory", ["python_output", "r_markdown_output"])
def test_verification_rejects_unlisted_managed_files(
    generated_release: updater.Config, directory: str
) -> None:
    """Stray files are forbidden even when they do not have a notebook extension."""
    config = generated_release
    (config.temp_prefix / getattr(config, directory) / "unexpected.txt").write_text("stale")
    with pytest.raises(ValueError, match="unexpected or missing"):
        updater.verify_output(config)


def test_verification_checks_python_syntax_even_with_matching_checksum(
    generated_release: updater.Config,
) -> None:
    """Checksums alone do not establish that a notebook can be parsed."""
    config = generated_release
    manifest_path = config.temp_prefix / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    name = manifest["resource_files"][0]["python"]
    path = config.temp_prefix / name
    notebook = json.loads(path.read_text())
    notebook["cells"].append(
        {"cell_type": "code", "source": ["def broken(\n"], "metadata": {}, "outputs": []}
    )
    path.write_text(json.dumps(notebook))
    manifest["files"][name] = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(SyntaxError):
        updater.verify_output(config)


def test_verification_rejects_symlinks_outside_managed_directories(
    generated_release: updater.Config, tmp_path: Path
) -> None:
    """Preserved static files must not smuggle symlinks into a publication."""
    target = tmp_path / "operator-file"
    target.write_text("private")
    (generated_release.temp_prefix / "static-link").symlink_to(target)
    with pytest.raises(ValueError, match="symbolic links"):
        updater.verify_output(generated_release)
    assert target.read_text() == "private"


def test_verify_cli_is_offline_read_only_and_fails_on_corruption(
    generated_release: updater.Config, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CI's actual command must verify output without regenerating or fetching it."""
    config = generated_release
    root = Path(__file__).resolve().parents[1]
    settings = yaml.safe_load((root / "config.yaml").read_text())
    settings["paths"]["temp_prefix"] = str(config.temp_prefix)
    config_path = tmp_path / "operator.yaml"
    config_path.write_text(yaml.safe_dump(settings))

    def unexpected_fetch(_: updater.Config) -> None:
        pytest.fail("--verify-output fetched catalogue metadata")

    monkeypatch.setattr(updater, "get_current_json", unexpected_fetch)
    monkeypatch.chdir(tmp_path)
    before = {
        p.relative_to(config.temp_prefix): p.read_bytes()
        for p in config.temp_prefix.rglob("*")
        if p.is_file()
    }
    runner = CliRunner()
    command = ["--config", str(config_path), "--verify-output"]
    result = runner.invoke(updater.app, command)
    assert result.exit_code == 0, result.exception
    assert before == {
        p.relative_to(config.temp_prefix): p.read_bytes()
        for p in config.temp_prefix.rglob("*")
        if p.is_file()
    }
    (config.temp_prefix / "index.md").unlink()
    result = runner.invoke(updater.app, command)
    assert result.exit_code != 0
    assert isinstance(result.exception, ValueError)
    assert "integrity" in str(result.exception)
    assert not (config.temp_prefix / "index.md").exists()
