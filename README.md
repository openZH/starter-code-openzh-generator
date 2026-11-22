# Starter Code Generator OpenZH

Generate Python notebooks and R Markdown files for CSV resources in the Canton of Zurich's open-data catalogue. Each file loads one resource and provides basic summaries and plots to help users start exploring the data.

**Looking for notebooks to use?** Browse [openZH/starter-code-openZH](https://github.com/openZH/starter-code-openZH). This repository maintains the generator behind them.

## How it works

The generator reads the catalogue metadata, selects resources listed as CSV, and fills the templates in [\_templates/](./_templates/). It writes notebooks and an overview with Colab, Python and R links to `_work/`. Data is downloaded when a notebook runs.

Python notebooks can run in Colab or a local notebook environment; R Markdown files need a local R environment with the packages used by the template. Check the inferred CSV separator and column types before using the data for analysis.

## Run locally

With `uv` installed, run from the repository root. The generator requires Python 3.13 or newer; the checkout and CI use Python 3.13.

```bash
uv sync --locked
uv run updater
uv run updater --verify-output
```

The Python package is `starter_code_openzh_generator`; `uv run python -m starter_code_openzh_generator` also runs the generator. The `updater` command remains available.

Find the generated files in `_work/02_python/` and `_work/01_r-markdown/`, and browse them through `_work/README.md`. The final command checks the generated output without downloading metadata or executing notebooks. Local runs do not publish anything.

**Generated notebook directories are rebuilt on every run.** Keep hand-written files outside them, and run only one generator per output directory at a time.

Generation stages and verifies the output before replacing it, preserving files outside the notebook directories except the generated `README.md`, `index.md` and `manifest.json`. If replacement or rollback is interrupted, a sibling `._work.previous` backup may remain. Inspect and recover that backup before rerunning; generation refuses to overwrite it. A custom output root uses the backup name `.<output-root-name>.previous`.

## Customize

Edit [config.yaml](config.yaml) to change catalogue settings, output paths, metadata fields or links to the published repository. Edit the files in [\_templates/](./_templates/) to change the overview and notebook content, preserving their template markers.

To use a different configuration:

```bash
uv run updater --config path/to/config.yaml
```

The default configuration is `config.yaml` in the working directory. Relative paths to configuration files, output roots (`paths.temp_prefix`) and template folders use the working directory, including when using `--config`. Notebook output subdirectories are relative to the output root; template filenames are relative to the template folder.

## Publish automatically

[The GitHub Actions workflow](.github/workflows/autoupdater.yml) generates and publishes notebooks from `main` on pushes, weekly, or when triggered manually. Quality checks and output verification must pass before publication.

To set up publishing:

1. Set the target account, repository and branch in both `config.yaml` and the workflow's publishing step. Keep its `source-directory` aligned with the configured output root.
2. Create a fine-grained personal access token with the target organization (`openZH` by default) as the resource owner. Select the target repository (`starter-code-openZH` by default) and grant **Contents → Read and write**. The token owner needs write access to the target repository, and the organization may require token approval. If you use a classic token, grant repository write access and authorize it for the organization if it uses SAML SSO. [GitHub token guide](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens)
3. In the generator repository, go to **Settings → Secrets and variables → Actions** and save the token as the repository secret `PAT`. The workflow passes it to the publishing action as `API_TOKEN_GITHUB`.
4. Use a target repository dedicated to generated output and review `_work/LICENSE.md` before publishing. Enable GitHub Pages in the target repository and deploy from the target branch's root. The generated `index.md` serves as the entry page.

### Troubleshoot publishing authentication

If the push reports `Invalid username or token`, check the publishing step's log. A masked `API_TOKEN_GITHUB: ***` shows that the action received a value. Check whether the token expired, was revoked, or lost access to the target repository. Update the `PAT` secret if the token value changed, then select **Re-run failed jobs**. Verify that the generated commit lands on the target branch. A run that reports `Everything up-to-date` had no changes to publish.

## Development

After `uv sync --locked`, run `make check` for formatting, lint and tests. Run `make help` for other commands. Automated checks do not execute R notebooks; test R template changes in an R environment.

## Related projects and contributions

Ideas and contributions are welcome through issues and pull requests.

This project is inspired by and based on the work of [Alexander](https://github.com/alexanderguentert), [Philipp](https://github.com/philbosch), [Stefan](https://github.com/metaodi/metaodi), [Adrian](https://github.com/adrianrupp88), [Laure](https://github.com/stadlaur), and [Patrick](https://github.com/rnckp).

Thanks to our colleagues at Stadt Zürich, who have substantially expanded on the original ideas with their advanced [starter-code project](https://github.com/opendatazurich/starter-code)!

Related projects include [starter notebooks for opendata.swiss](https://github.com/rnckp/starter-code_opendataswiss) and the [OGD Thurgau starter code generator](https://github.com/ogdtg/starter-code-ogdtg).
