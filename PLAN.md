# Follow-up work

- Review F03: Verify that each manifest resource ID pair maps to its expected Python and R filenames, using the existing deterministic naming rule. Add regressions for swapped file references and changed resource IDs with unchanged paths; preserve the manifest format and filename compatibility. See [F03 in REVIEW.md](REVIEW.md#f03--verification-does-not-validate-the-resource-to-file-association).
- Define linting for notebook templates: repository-wide Ruff checks report unresolved template placeholders. The current package/test check commands are in [README.md](README.md#development); template code is exercised by offline Python tests.
- Execute the R Markdown EDA in an R environment with current tidyverse and skimr, including empty and all-missing datasets, CSV loading, HTTP headers and temporary-file cleanup. Current automated checks validate generated R content only.
- Enable/verify Pages deployment from the output repository root; this change generates `index.md` but does not change remote repository settings.
