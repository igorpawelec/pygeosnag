# Contributing to pygeosnag

Contributions are welcome! Here's how to get started.

## Setup

```bash
git clone https://github.com/igorpawelec/pygeosnag.git
cd pygeosnag
conda env create -f environment.yaml
conda activate pygeosnag
pip install -e . --no-deps
```

## Development workflow

1. Create a feature branch: `git checkout -b feature/my-feature`
2. Make changes
3. Run the test script: `python pycrown_test.py` (or your own test data)
4. Commit: `git commit -m "Add my feature"`
5. Push: `git push origin feature/my-feature`
6. Open a Pull Request on GitHub

## Code style

- Follow PEP 8
- Use type hints where practical
- Numba `@njit(cache=True)` for performance-critical code
- Docstrings in NumPy style

## Releasing

The checklist exists because of a specific failure. `max_iters` changed
default in 0.3.0, and that one change broke CI in two packages at once —
pycacumen with `int | None`, which is a runtime `TypeError` before Python 3.10
while the metadata claims `>=3.9`, and rcacumen with a stale `man/` page. Neither
was noticed. **pycacumen then tagged 0.3.0, 0.4.0 and 0.5.0 with the workflow
red**, so three releases could not be imported on the minimum Python they
advertise. rcacumen shipped two the same way, rgeoadaptels two more.

Local tests passed in every one of those cases. They were run on one
interpreter, on one operating system, by someone who already knew what the
change was meant to do. The matrix is the part that disagrees.

1. Update `CHANGELOG.md`. If the output changes, say so in those words.
2. Bump the version everywhere it appears. Search for the *old* number and
   read the hits — `grep -rn "0.4.0" --exclude-dir=.git` — rather than
   editing the two or three places you remember.
3. Run the tests locally.
   Mind the oldest Python in `requires-python`: `X | Y` in an annotation
   is a runtime expression before 3.10 and will not import there, however
   cleanly it runs on your interpreter.
4. Commit and push. **Do not tag yet.**
5. **Wait for Actions on the pushed commit and confirm every matrix job is
   green.** Not the previous run, not the branch generally — that commit.
   This is the step that was missing. Either open the Actions tab, or:

   ```bash
   curl -s "https://api.github.com/repos/OWNER/REPO/actions/runs?per_page=1" |
     python -c "import json,sys; r=json.load(sys.stdin)['workflow_runs'][0]; print(r['head_sha'][:7], r['status'], r['conclusion'])"
   ```

   `gh run list` is nicer if the GitHub CLI is installed; it is not
   everywhere, and the curl form needs nothing but a public repo.
6. Only then tag and push the tag:
   `git tag -a vX.Y.Z -m "..." && git push --tags`
7. If this release changes what the package produces, bump the pin in
   [rgeoadaptels](https://github.com/igorpawelec/rgeoadaptels)'s
   `.github/workflows/R-CMD-check.yaml`, which installs `pygeosnag` from a tag.
   Leaving it stale does not break anything visibly — the R twin goes on
   proving its agreement against the previous release, which is exactly the
   kind of quiet staleness this checklist exists to prevent.

The order matters. A tag is what people install and what a DOI points at, so
it should never be the thing that discovers a broken build. If Actions is
red, fix it and release the fix as its own version — the broken tag stays in
history either way.

## Reporting bugs

Open an issue on GitHub with:
- Python, NumPy, Numba, Rasterio versions
- Minimal reproducible example
- Full traceback

## License

By contributing you agree that your contributions will be licensed under GPLv3.
