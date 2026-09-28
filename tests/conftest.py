"""Shared catalogue and filesystem fixtures; no external services."""

from dataclasses import replace
from pathlib import Path

import pandas as pd
import pytest

from starter_code_openzh_updater import updater


@pytest.fixture
def config(tmp_path: Path) -> updater.Config:
    """Use actual templates and isolated output."""
    root = Path(__file__).resolve().parents[1]
    return replace(
        updater.Config.from_yaml(root / "config.yaml"),
        template_folder=root / "_templates",
        temp_prefix=tmp_path / "output",
    )


@pytest.fixture
def catalogue() -> pd.DataFrame:
    """Two CSV resources with URL suffixes deliberately unrelated to format."""
    return pd.DataFrame(
        [
            {
                "identifier": "123@example",
                "title": 'Title "quoted" | <script>bad</script>',
                "description": 'A backslash \\ and {{ CONTACT }}\n```{r}\nstop("bad")\n```',
                "contactPoint": [{"name": "Example"}],
                "distribution": [
                    {
                        "ktzhDistId": "one",
                        "title": "CSV | resource",
                        "format": "csv",
                        "downloadUrl": "https://example.invalid/download?name=a'b&x=1",
                    },
                    {
                        "ktzhDistId": "two",
                        "title": "Second CSV resource",
                        "format": " CSV ",
                        "downloadUrl": "https://example.invalid/second-download",
                    },
                ],
            }
        ]
    )


@pytest.fixture
def generated_release(
    config: updater.Config, catalogue: pd.DataFrame, monkeypatch: pytest.MonkeyPatch
) -> updater.Config:
    """Build real artifacts while replacing only the remote catalogue fetch."""
    monkeypatch.setattr(updater, "get_current_json", lambda _: catalogue)
    updater.run_update(config)
    return config
