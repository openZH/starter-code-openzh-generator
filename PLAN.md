# Follow-up work

- Verify that each manifest resource ID pair maps to its expected Python and R filenames, using the existing deterministic naming rule. The four cases in `test_verification_rejects_incorrect_resource_file_associations` currently fail: verification accepts swapped Python/R references and changed dataset/resource IDs with unchanged paths. Fix production validation while preserving the manifest format and filename compatibility.
- Remove the temporary certifi cooldown exception from `pyproject.toml` and refresh/validate `uv.lock`, retaining `certifi>=2026.10.19`. The locked 2026.10.23 artifacts have passed the seven-day cooldown. See [the remediation note](NOTES.md#emudhraemsign-ca-remediation-2026-10-26).
- Define linting for notebook templates: repository-wide Ruff checks report unresolved template placeholders. The current package/test check commands are in [README.md](README.md#development); template code is exercised by offline Python tests.
- Execute the R Markdown EDA in an R environment with current tidyverse and skimr, including empty and all-missing datasets, CSV loading, HTTP headers and temporary-file cleanup. Current automated checks validate generated R content only.
- Enable/verify Pages deployment from the output repository root; the generator writes `index.md` but does not change remote repository settings.
