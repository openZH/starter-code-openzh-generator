"""Regression tests for generated starter notebooks."""

import json
import re
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pandas as pd
import pytest
import yaml

from starter_code_openzh_generator.updater import (
    Config,
    create_python_notebooks,
    create_rmarkdown,
    prepare_data_for_codebooks,
)


@pytest.mark.parametrize(
    "command", [["updater"], [sys.executable, "-m", "starter_code_openzh_generator"]]
)
@pytest.mark.parametrize("terminal", ["dumb", "xterm-256color"], ids=["plain", "colored"])
def test_installed_cli_help_works_outside_checkout(
    tmp_path: Path, command: list[str], terminal: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both entry points show plain and colored help without a local config file."""
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("TERM", terminal)
    monkeypatch.delenv("_TYPER_FORCE_DISABLE_TERMINAL", raising=False)
    result = subprocess.run(
        [*command, "--help"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    # Typer inserts ANSI style sequences inside option names on GitHub Actions.
    help_text = re.sub(r"\x1b\[[0-9;]*m", "", result.stdout)
    assert "--config" in help_text
    assert "--verbose" in help_text


def test_default_config_is_loaded_from_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An installed generator reads the operator's config, not package files."""
    root = Path(__file__).resolve().parents[1]
    settings = yaml.safe_load((root / "config.yaml").read_text(encoding="utf-8"))
    settings["data_shop"]["provider"] = "Local provider"
    settings["paths"]["template_folder"] = "local-templates"
    settings["paths"]["temp_prefix"] = "local-output"
    (tmp_path / "config.yaml").write_text(
        yaml.safe_dump(settings),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    config = Config.from_yaml()

    assert config.provider == "Local provider"
    assert config.template_folder == Path("local-templates")
    assert config.temp_prefix == Path("local-output")


def test_missing_default_config_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Do not silently fall back to configuration in the source checkout."""
    monkeypatch.chdir(tmp_path)
    with pytest.raises(FileNotFoundError, match="Configuration file not found"):
        Config.from_yaml()


@pytest.mark.parametrize(("distribution_count", "selected_index"), [(1, 0), (2, 0), (2, 1)])
def test_python_notebook_contains_each_section_once(
    tmp_path: Path, distribution_count: int, selected_index: int
) -> None:
    """Generate one complete notebook without repeating its cells or CSV loads."""
    root = Path(__file__).resolve().parents[1]
    config = replace(
        Config.from_yaml(root / "config.yaml"),
        template_folder=root / "_templates",
        temp_prefix=tmp_path,
    )
    links = [f"https://example.invalid/data-{i}.csv" for i in range(distribution_count)]
    data = pd.DataFrame(
        [
            {
                "identifier": "123@example",
                "title": "Example dataset",
                "description": "Sample metadata for offline generation.",
                "contactPoint": "Example contact",
                "distribution": [
                    {
                        "ktzhDistId": str(i),
                        "title": f"Resource {i}",
                        "format": "csv",
                        "downloadUrl": link,
                    }
                    for i, link in enumerate(links)
                ],
            }
        ]
    )

    data = prepare_data_for_codebooks(data, config)
    create_python_notebooks(data, config)
    create_rmarkdown(data, config)

    assert len(list((tmp_path / config.python_output).glob("*.ipynb"))) == distribution_count
    filename = data.iloc[selected_index]["filename"]
    output = tmp_path / config.python_output / f"{filename}.ipynb"
    notebook = json.loads(output.read_text(encoding="utf-8"))
    sources = ["".join(cell["source"]) for cell in notebook["cells"]]
    headings = [
        source.splitlines()[0]
        for cell, source in zip(notebook["cells"], sources, strict=True)
        if cell["cell_type"] == "markdown"
    ]
    assert headings == [
        f"## Open government data provided by **{config.provider}**",
        "## Dataset",
        "## Description",
        "## Dataset links",
        "## Metadata",
        "## Imports and helper functions",
        "## Load data",
        "## Analyze data",
        "### Next steps",
        "**Questions about the data?** Example contact",
    ]
    code_sources = [
        source.strip()
        for cell, source in zip(notebook["cells"], sources, strict=True)
        if cell["cell_type"] == "code" and source.strip()
    ]
    code = "\n".join(code_sources)
    assert code.count("df = get_dataset(") == 1
    assert links[selected_index] in code
    for link in links[:selected_index] + links[selected_index + 1 :]:
        assert link not in code
    assert code.count("def get_dataset(") == 1
    assert code.count("df.head()") == 1
    assert code.count("sns.histplot(") == 1
    assert "{{ " not in "\n".join(sources)
    rmarkdown = (tmp_path / config.r_markdown_output / f"{filename}.Rmd").read_text()
    assert "{{ " not in rmarkdown
    assert "stop_for_problems(data)" in rmarkdown
    assert "skim(df)" in rmarkdown
    assert "geom_col(" in rmarkdown
    assert rmarkdown.count("df <- get_dataset(") == 1
    assert links[selected_index] in rmarkdown
    for link in links[:selected_index] + links[selected_index + 1 :]:
        assert link not in rmarkdown
