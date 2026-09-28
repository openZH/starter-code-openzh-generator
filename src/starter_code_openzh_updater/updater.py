"""
Starter Code Generator for Open Government Data Shops.

Automatically generates Python Jupyter Notebooks and R Markdown files
from the JSON metadata of an open data catalogue.
"""

from __future__ import annotations

import ast
import hashlib
import html
import json
import logging
import re
import shutil
import tempfile
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit

import pandas as pd
import requests
import typer
import yaml

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)
TEMPLATE_MARKER = re.compile(r"{{\s*([A-Z_]+)\s*}}")


# CONFIGURATION -------------------------------------------------------------- #


@dataclass
class Config:
    """Configuration container for the starter code generator."""

    # Paths (all as Path objects for consistency)
    template_folder: Path
    temp_prefix: Path
    r_markdown_output: Path
    python_output: Path

    # Templates
    template_header: str
    template_readme: str
    template_python: str
    template_rmarkdown: str

    # Data shop settings
    provider: str
    metadata_link: str
    base_link: str
    root_key: str

    # GitHub settings
    github_account: str
    repo_name: str
    repo_branch: str

    # Display settings
    title_max_chars: int

    # HTTP settings
    http_timeout: int

    user_agent_generator: str = "OpenZH-StarterCode-Generator/1.0"
    user_agent_python: str = "OpenZH-StarterCode-Python/1.0"
    user_agent_r: str = "OpenZH-StarterCode-R/1.0"

    # Metadata keys
    keys_dataset: list[str] = field(default_factory=list)
    keys_distribution: list[str] = field(default_factory=list)

    @classmethod
    def from_yaml(cls, config_path: Path | None = None) -> Config:
        """Load the given YAML file, defaulting to config.yaml in the working directory."""
        if config_path is None:
            config_path = Path("config.yaml")

        if not config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_path}")

        with open(config_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        return cls(
            # Paths - all as Path objects
            template_folder=Path(data["paths"]["template_folder"]),
            temp_prefix=Path(data["paths"]["temp_prefix"]),
            r_markdown_output=Path(data["paths"]["r_markdown_output"]),
            python_output=Path(data["paths"]["python_output"]),
            # Templates
            template_header=data["templates"]["header"],
            template_readme=data["templates"]["readme"],
            template_python=data["templates"]["python"],
            template_rmarkdown=data["templates"]["rmarkdown"],
            # Data shop
            provider=data["data_shop"]["provider"],
            metadata_link=data["data_shop"]["metadata_link"],
            base_link=data["data_shop"]["base_link"],
            root_key=data["data_shop"]["root_key"],
            # GitHub
            github_account=data["github"]["account"],
            repo_name=data["github"]["repo_name"],
            repo_branch=data["github"]["branch"],
            # Display
            title_max_chars=data["display"]["title_max_chars"],
            # HTTP
            http_timeout=data["http"]["timeout_seconds"],
            user_agent_generator=data["http"]["user_agent_generator"],
            user_agent_python=data["http"]["user_agent_python"],
            user_agent_r=data["http"]["user_agent_r"],
            # Metadata keys
            keys_dataset=data["metadata_keys"]["dataset"],
            keys_distribution=data["metadata_keys"]["distribution"],
        )


# GENERATION ----------------------------------------------------------------- #


def safe_identifier(value: object) -> str:
    """Require a bounded, portable identifier before using it in paths."""
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9@._-]{0,119}", value):
        raise ValueError("Invalid dataset or resource identifier")
    return value


def http_url(value: object) -> str:
    """Reject non-HTTP URLs, credentials and control characters."""
    if not isinstance(value, str) or any(ord(c) <= 32 or ord(c) == 127 for c in value):
        raise ValueError("Invalid HTTP URL")
    parts = urlsplit(value)
    if (
        parts.scheme not in {"https", "http"}
        or not parts.hostname
        or parts.username
        or parts.password
    ):
        raise ValueError("Invalid HTTP URL")
    return value


def markdown(value: object) -> str:
    """Render catalogue text and list values as safe, literal Markdown."""
    text = ", ".join(str(item) for item in value) if isinstance(value, list) else str(value)
    # Escape original characters once; re-escaping '#' would corrupt apostrophe entities.
    return (
        re.sub(
            r"""[&<>"'\\`*_{}\[\]()|!#~$]""",
            lambda m: html.escape(m[0], quote=True) if m[0] in "&<>\"'" else f"&#{ord(m[0])};",
            text,
        )
        .replace("\n", "<br>")
        .replace("\r", "")
    )


def metadata_value(key: str, value: object) -> str:
    """Format issued/modified timestamps for display and escape metadata values."""
    if key in {"issued", "modified"} and isinstance(value, str):
        # Change only the separator, preserving the source timezone and precision.
        value = re.sub(r"^([0-9]{4}-[0-9]{2}-[0-9]{2})T(?=[0-9]{2}:[0-9]{2})", r"\1 ", value)
    return markdown(value)


def link_url(url: str) -> str:
    """Encode characters that could terminate a Markdown link."""
    return quote(url, safe=":/?=&%+@#;-._~")


def validate_config(config: Config) -> None:
    """Constrain managed directories and HTTP configuration."""
    paths = [config.python_output, config.r_markdown_output]
    for path in paths:
        if path.is_absolute() or len(path.parts) != 1 or path.name in {"", ".", ".."}:
            raise ValueError("Output subdirectories must be distinct single directory names")
    if paths[0] == paths[1]:
        raise ValueError("Output subdirectories must be distinct")
    root = config.temp_prefix.resolve()
    if root == Path.cwd() or root in Path.cwd().parents or config.temp_prefix.is_symlink():
        raise ValueError("Unsafe output root")
    for name in (
        config.template_header,
        config.template_readme,
        config.template_python,
        config.template_rmarkdown,
    ):
        if Path(name).name != name:
            raise ValueError("Template filenames must be basenames")
    http_url(config.metadata_link)
    http_url(config.base_link)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}", config.github_account):
        raise ValueError("Invalid GitHub account")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}", config.repo_name):
        raise ValueError("Invalid GitHub repository")
    if config.http_timeout <= 0 or config.title_max_chars <= 0:
        raise ValueError("Timeout and title length must be positive")
    for value in (config.user_agent_generator, config.user_agent_python, config.user_agent_r):
        if not value or any(ord(c) < 32 or ord(c) > 126 for c in value):
            raise ValueError("User-Agent must be printable ASCII")


def get_current_json(config: Config) -> pd.DataFrame:
    """Fetch the catalogue with an identifiable User-Agent and timeout."""
    with requests.get(
        config.metadata_link,
        timeout=config.http_timeout,
        headers={"User-Agent": config.user_agent_generator},
    ) as response:
        response.raise_for_status()
        payload = response.json()
    if not isinstance(payload, dict) or not isinstance(payload.get(config.root_key), list):
        raise ValueError("Catalogue must contain a dataset list")
    return pd.DataFrame(payload[config.root_key])


def prepare_data_for_codebooks(data: pd.DataFrame, config: Config) -> pd.DataFrame:
    """Validate catalogue boundaries and produce one row per CSV distribution.

    Args:
        data: Catalogue rows containing nested distribution dictionaries.
        config: Metadata fields to display.

    Returns:
        Resource rows with stable filenames and escaped display metadata.

    Raises:
        ValueError: Identifiers, URLs or structures are invalid, IDs collide, or
            the catalogue contains no CSV resources.
    """
    resources = []
    datasets_seen: set[str] = set()
    filenames_seen: set[str] = set()
    for row in data.to_dict("records"):
        identifier = safe_identifier(row.get("identifier"))
        if identifier.casefold() in datasets_seen:
            raise ValueError("Duplicate dataset identifier")
        datasets_seen.add(identifier.casefold())
        distributions = row.get("distribution")
        if distributions is None:
            continue
        if not isinstance(distributions, list):
            raise ValueError("Dataset distributions must be a list")
        contact = row.get("contactPoint")
        if isinstance(contact, list):
            contact = " | ".join(
                str(value)
                for item in contact
                if isinstance(item, dict)
                for value in item.values()
                if value is not None
            )
        for dist in distributions:
            if not isinstance(dist, dict):
                raise ValueError("Distribution must be an object")
            if str(dist.get("format", "")).strip().lower() != "csv":
                continue
            url = http_url(dist.get("downloadUrl"))
            # Prefer catalogue IDs; URL hashing is deterministic if an ID is absent.
            raw_id = dist.get("ktzhDistId")
            resource_id = (
                safe_identifier(str(raw_id))
                if raw_id is not None
                else f"url-{hashlib.sha256(url.encode()).hexdigest()[:12]}"
            )
            filename = f"{identifier}--{resource_id}"
            # Also reject ambiguous separators, case-folding and fallback collisions.
            if filename.casefold() in filenames_seen:
                raise ValueError("Duplicate resource identifier or filename collision")
            filenames_seen.add(filename.casefold())
            metadata = "\n".join(
                f"- **{markdown(k)}:** {metadata_value(k, row.get(k, ''))}"
                for k in config.keys_dataset
            )
            metadata += "\n" + "\n".join(
                f"- **Resource {markdown(k)}:** {metadata_value(k, dist.get(k, ''))}"
                for k in config.keys_distribution
            )
            resources.append(
                {
                    "identifier": identifier,
                    "resource_id": resource_id,
                    "filename": filename,
                    "title": str(row.get("title", identifier)),
                    "description": str(row.get("description", "")),
                    "resource_title": str(dist.get("title") or resource_id),
                    "url": url,
                    "metadata": metadata,
                    "contact": str(contact or ""),
                }
            )
    if not resources:
        raise ValueError("No CSV resources; refusing to publish an empty release")
    return (
        pd.DataFrame(resources)
        .sort_values(["title", "identifier", "resource_id"])
        .reset_index(drop=True)
    )


def apply_template_replacements(template: str, replacements: dict[str, str]) -> str:
    """Replace whitespace-tolerant markers once without reprocessing inserted metadata."""

    def substitute(match: re.Match[str]) -> str:
        key = match[1]
        if key not in replacements:
            raise ValueError(f"Unknown template marker: {key}")
        return replacements[key]

    return TEMPLATE_MARKER.sub(substitute, template)


def replacements_for(row: dict[str, Any], config: Config) -> dict[str, str]:
    """Prepare text for Markdown contexts only."""
    catalogue = link_url(config.base_link + quote(row["identifier"], safe=""))
    return {
        "PROVIDER": markdown(config.provider),
        "DATASET_TITLE": markdown(row["title"]),
        "DATASET_IDENTIFIER": markdown(row["identifier"]),
        "DATASET_DESCRIPTION": markdown(row["description"]),
        "DATASET_METADATA": row["metadata"],
        "CONTACT": markdown(row["contact"]),
        "RESOURCE_TITLE": markdown(row["resource_title"]),
        "TODAY_DATE": datetime.now().strftime("%Y-%m-%d"),
        "DATASHOP_URL": catalogue,
    }


def create_python_notebooks(data: pd.DataFrame, config: Config) -> None:
    """Render parsed JSON cells, escaping code literals separately from Markdown."""
    template = json.loads((config.template_folder / config.template_python).read_text())
    output = config.temp_prefix / config.python_output
    output.mkdir(parents=True, exist_ok=True)
    for row in data.to_dict("records"):
        notebook = json.loads(json.dumps(template))
        replacements = replacements_for(row, config)
        markers = 0
        for cell in notebook["cells"]:
            source = cell["source"]
            source = "".join(source) if isinstance(source, list) else source
            if cell["cell_type"] == "code":
                markers += TEMPLATE_MARKER.findall(source).count("DISTRIBUTION")
                source = apply_template_replacements(
                    source,
                    {
                        "USER_AGENT_LITERAL": json.dumps(config.user_agent_python),
                        "TIMEOUT_LITERAL": str(config.http_timeout),
                        "DISTRIBUTION": (
                            f"df = get_dataset({json.dumps(row['url'], ensure_ascii=False)})"
                        ),
                    },
                )
                ast.parse(source)
                cell["execution_count"] = None
                cell["outputs"] = []
            else:
                source = apply_template_replacements(source, replacements)
            cell["source"] = source.splitlines(keepends=True)
        if markers != 1:
            raise ValueError("Python template must contain exactly one distribution marker")
        (output / f"{row['filename']}.ipynb").write_text(
            json.dumps(notebook, ensure_ascii=False, indent=2) + "\n"
        )


def create_rmarkdown(data: pd.DataFrame, config: Config) -> None:
    """Render R Markdown using escaped text and quoted R string literals."""
    template = (config.template_folder / config.template_rmarkdown).read_text()
    if TEMPLATE_MARKER.findall(template).count("DISTRIBUTIONS") != 1:
        raise ValueError("R template must contain exactly one distribution marker")
    output = config.temp_prefix / config.r_markdown_output
    output.mkdir(parents=True, exist_ok=True)
    for row in data.to_dict("records"):
        values = replacements_for(row, config)
        values.update(
            {
                "USER_AGENT_LITERAL": json.dumps(config.user_agent_r),
                "TIMEOUT_LITERAL": str(config.http_timeout),
                "DISTRIBUTIONS": (
                    f"df <- get_dataset({json.dumps(row['url'], ensure_ascii=False)})"
                ),
            }
        )
        (output / f"{row['filename']}.Rmd").write_text(
            apply_template_replacements(template, values)
        )


def github_file(config: Config, directory: Path, filename: str) -> str:
    """Build a GitHub file link using encoded path segments."""
    parts = [
        config.github_account,
        config.repo_name,
        "blob",
        config.repo_branch,
        str(directory),
        filename,
    ]
    return "https://github.com/" + "/".join(quote(p, safe="") for p in parts)


def create_overview(data: pd.DataFrame, config: Config) -> None:
    """Write the full resource table to README and Pages."""
    header = (config.template_folder / config.template_header).read_text()
    header = apply_template_replacements(
        header,
        {
            "DATASET_COUNT": str(data["identifier"].nunique()),
            "RESOURCE_COUNT": str(len(data)),
            "TODAY_DATE": datetime.now().strftime("%Y-%m-%d"),
        },
    )
    lines = [
        "\n| Dataset | Resource | Colab | Python | R |\n| :-- | :-- | :-- | :-- | :-- |\n",
    ]
    for row in data.to_dict("records"):
        py = github_file(config, config.python_output, row["filename"] + ".ipynb")
        r = github_file(config, config.r_markdown_output, row["filename"] + ".Rmd")
        colab = py.replace("https://github.com/", "https://colab.research.google.com/github/", 1)
        r_link = f"[R Markdown]({r})"
        title = markdown(row["title"][: config.title_max_chars])
        resource = markdown(row["resource_title"])
        catalogue = link_url(config.base_link + quote(row["identifier"], safe=""))
        lines.append(
            f"| [{title}]({catalogue}) | {resource} | [Colab]({colab}) | "
            f"[Notebook]({py}) | {r_link} |\n"
        )
    table = "".join(lines)
    (config.temp_prefix / "index.md").write_text(header + table)
    pages = f"https://{config.github_account}.github.io/{quote(config.repo_name, safe='')}/"
    readme = (config.template_folder / config.template_readme).read_text()
    (config.temp_prefix / "README.md").write_text(
        apply_template_replacements(
            readme, {"HEADER": header, "PAGES_URL": pages, "RESOURCE_TABLE": table}
        )
    )


def write_manifest(data: pd.DataFrame, config: Config) -> None:
    """Record every expected artifact and its checksum after generation."""
    names = ["README.md", "index.md"]
    stems = data["filename"]
    for directory, extension in [
        (config.python_output, ".ipynb"),
        (config.r_markdown_output, ".Rmd"),
    ]:
        names.extend(str(directory / (stem + extension)) for stem in stems)
    manifest = {
        "version": 1,
        "resources": len(data),
        "datasets": data["identifier"].nunique(),
        "resource_files": [
            {
                "dataset_id": row["identifier"],
                "resource_id": row["resource_id"],
                "python": str(config.python_output / (row["filename"] + ".ipynb")),
                "r": str(config.r_markdown_output / (row["filename"] + ".Rmd")),
            }
            for row in data.to_dict("records")
        ],
        "files": {
            name: hashlib.sha256((config.temp_prefix / name).read_bytes()).hexdigest()
            for name in names
        },
    }
    (config.temp_prefix / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


def verify_output(config: Config) -> None:
    """Reject missing, unexpected or modified generated artifacts before publishing.

    Args:
        config: Output root and managed notebook directories to verify.

    Raises:
        ValueError: Manifest mappings, counts or checksums do not match output.
        OSError: A manifest or generated file cannot be read.
        SyntaxError: A generated Python code cell is invalid.
    """
    validate_config(config)
    root = config.temp_prefix
    if any(p.is_symlink() for p in root.rglob("*")):
        raise ValueError("Output must not contain symbolic links")
    manifest = json.loads((root / "manifest.json").read_text())
    files = manifest["files"]
    if manifest["version"] != 1 or manifest["resources"] < 1 or manifest["datasets"] < 1:
        raise ValueError("Invalid output manifest")
    expected_count = manifest["resources"]
    entries = manifest["resource_files"]
    if len(entries) != manifest["resources"]:
        raise ValueError("Output integrity check failed: resource mapping")
    expected_files = {"README.md", "index.md"}
    pairs = set()
    for entry in entries:
        dataset = safe_identifier(entry["dataset_id"])
        resource = safe_identifier(entry["resource_id"])
        pairs.add((dataset, resource))
        expected_files.update([entry["python"], entry["r"]])
    if (
        len(pairs) != len(entries)
        or len({dataset for dataset, _ in pairs}) != manifest["datasets"]
        or expected_files != files.keys()
    ):
        raise ValueError("Output integrity check failed: resource mapping")
    if len(files) != 2 + 2 * expected_count or not {"README.md", "index.md"} <= files.keys():
        raise ValueError("Output integrity check failed: manifest counts")
    for name, checksum in files.items():
        path = Path(name)
        if path.is_absolute() or ".." in path.parts or (root / path).is_symlink():
            raise ValueError("Unsafe manifest path")
        if (
            not (root / path).is_file()
            or hashlib.sha256((root / path).read_bytes()).hexdigest() != checksum
        ):
            raise ValueError("Output integrity check failed")
        if path.suffix == ".ipynb":
            notebook = json.loads((root / path).read_text())
            for cell in notebook["cells"]:
                if cell["cell_type"] == "code":
                    ast.parse("".join(cell["source"]))
    for directory, extension in [
        (config.python_output, ".ipynb"),
        (config.r_markdown_output, ".Rmd"),
    ]:
        actual = {str(p.relative_to(root)) for p in (root / directory).iterdir()}
        expected = {
            name
            for name in files
            if Path(name).parent == directory and Path(name).suffix == extension
        }
        if len(expected) != expected_count or actual != expected:
            raise ValueError("Output integrity check failed: unexpected or missing files")


def run_update(config: Config) -> None:
    """Stage and validate a complete release, then replace output with rollback.

    Args:
        config: Catalogue, templates and publication output configuration.

    Raises:
        ValueError: Configuration, catalogue or generated output is invalid.
        OSError: Output cannot be written or replaced. Failed rollback retains
            the previous release in a sibling backup for manual recovery.
        requests.RequestException: The catalogue request fails.
    """
    validate_config(config)
    data = prepare_data_for_codebooks(get_current_json(config), config)
    root = config.temp_prefix.absolute()
    root.parent.mkdir(parents=True, exist_ok=True)
    # Keep recovery data outside TemporaryDirectory: even a failed rollback must
    # not allow context-manager cleanup to delete the previous release.
    backup = root.with_name(f".{root.name}.previous")
    if backup.exists():
        raise ValueError(f"Previous release backup exists; recover it before running: {backup}")
    with tempfile.TemporaryDirectory(prefix=".starter-release-", dir=root.parent) as temp:
        stage = Path(temp) / "output"
        if root.exists():
            if any(p.is_symlink() for p in root.rglob("*")):
                raise ValueError("Output must not contain symbolic links")
            shutil.copytree(root, stage)
        else:
            stage.mkdir()
        staged = replace(config, temp_prefix=stage)
        for directory in (staged.python_output, staged.r_markdown_output):
            if (stage / directory).exists():
                shutil.rmtree(stage / directory)
        create_python_notebooks(data, staged)
        create_rmarkdown(data, staged)
        create_overview(data, staged)
        write_manifest(data, staged)
        verify_output(staged)
        if root.exists():
            root.rename(backup)
        try:
            stage.rename(root)
        except OSError:
            if backup.exists():
                backup.rename(root)
            raise
        if backup.exists():
            shutil.rmtree(backup)
    logger.info("Generated and verified %d resources", len(data))


app = typer.Typer(name="updater", help="Generate Python and R starter notebooks.")


@app.command()
def update(
    config_file: Path | None = typer.Option(
        None, "--config", "-c", help="Configuration YAML file."
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose logging."),
    verify_only: bool = typer.Option(
        False, "--verify-output", help="Verify output without fetching metadata."
    ),
) -> None:
    """Generate starter notebooks or verify a staged publication."""
    if verbose:
        logger.setLevel(logging.DEBUG)
    config = Config.from_yaml(config_file)
    if verify_only:
        verify_output(config)
    else:
        run_update(config)
