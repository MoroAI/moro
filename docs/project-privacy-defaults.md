# Git protection for newly initialized projects

`moro init` now generates ignore rules for raw dataset contents, `.env` and
`.env.*`, Safetensors and GGUF weights, and common adapter/PyTorch `.bin` weight
names. The raw-data `.gitkeep` remains trackable, as do project configuration and
evaluation suites. Git itself exercises these rules in the regression tests.

Existing projects are not rewritten. To adopt the defaults, review and merge the
patterns from `src/moro/templates/project.py` into the project's `.gitignore`.
Do not use `moro init --force` solely to update ignores: it also overwrites other
project files. Ignore rules do not untrack previously committed files or remove
them from Git history, and explicit force-add can bypass them.

These defaults reduce accidental staging; they do not scan arbitrary filenames
for secrets, redact training data, or establish comprehensive privacy guarantees.
