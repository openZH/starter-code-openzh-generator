# Follow-up work

- Define linting for notebook templates: repository-wide Ruff checks report unresolved template placeholders. The current package/test check commands are in [README.md](README.md#development); template code is exercised by offline Python tests.
- Execute the R Markdown EDA in an R environment with current tidyverse and skimr, including empty and all-missing datasets, CSV loading, HTTP headers and temporary-file cleanup. Current automated checks validate generated R content only.
- Enable/verify Pages deployment from the output repository root; the generator writes `index.md` but does not change remote repository settings.
