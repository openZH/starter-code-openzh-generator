# Starter Code Generator OpenZH

Generate Python notebooks and R Markdown files for CSV resources in the Canton of Zurich's open-data catalogue. Each file loads one resource and provides basic summaries and plots to help users start exploring the data.

**Looking for notebooks to use?** Browse [openZH/starter-code-openZH](https://github.com/openZH/starter-code-openZH). This repository maintains the generator behind them.

## How it works

The generator reads the catalogue metadata, selects resources listed as CSV, and fills the templates in [\_templates/](./_templates/). It writes notebooks and an overview with Colab, Python and R links to `_work/`. Data is downloaded when a notebook runs.

Python notebooks can run in Colab or a local notebook environment; R Markdown files need a local R environment with the packages used by the template. Check the inferred CSV separator and column types before using the data for analysis.

## Run locally

With `uv` installed, run from the repository root:

```bash
uv sync --locked
uv run updater
uv run updater --verify-output
```

Find the generated files in `_work/02_python/` and `_work/01_r-markdown/`, and browse them through `_work/README.md`. The final command checks the generated output without downloading metadata or executing notebooks. Local runs do not publish anything.

**Generated notebook directories are rebuilt on every run.** Keep hand-written files outside them, and run only one generator per output directory at a time.

## Customize

Edit [config.yaml](config.yaml) to change catalogue settings, output paths, metadata fields or links to the published repository. Edit the files in [\_templates/](./_templates/) to change the overview and notebook content, preserving their template markers.

To use a different configuration:

```bash
uv run updater --config path/to/config.yaml
```

Relative paths are resolved from the working directory, including when using `--config`.

## Publish automatically

[The GitHub Actions workflow](.github/workflows/autoupdater.yml) generates and publishes notebooks from `main` on pushes, weekly, or when triggered manually. Quality checks and output verification must pass before publication.

To set up publishing:

1. Set the target account, repository and branch in both `config.yaml` and the workflow's publishing step. Keep its `source-directory` aligned with the configured output root.
2. Add a `PAT` Actions secret with write access to the target repository. Use a repository dedicated to generated output and review `_work/LICENSE.md` before publishing.
3. Enable GitHub Pages in the target repository, deploying from the target branch's root. The generated `index.md` serves as the entry page.

## Development

After `uv sync --locked`, run `make check` for formatting, lint and tests. Run `make help` for other commands. Automated checks do not execute R notebooks; test R template changes in an R environment.

## Related projects and contributions

Ideas and contributions are welcome through issues and pull requests.

This project is inspired by and based on the work of [Alexander](https://github.com/alexanderguentert), [Philipp](https://github.com/philbosch), [Stefan](https://github.com/metaodi/metaodi), [Adrian](https://github.com/adrianrupp88), [Laure](https://github.com/stadlaur), and [Patrick](https://github.com/rnckp).

Thanks to our colleagues at Stadt Zürich, who have substantially expanded on the original ideas with their advanced [starter-code project](https://github.com/opendatazurich/starter-code)!

Related projects include [starter notebooks for opendata.swiss](https://github.com/rnckp/starter-code_opendataswiss) and the [OGD Thurgau starter code generator](https://github.com/ogdtg/starter-code-ogdtg).
