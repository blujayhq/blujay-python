# Contributing

Most of this library is generated from the Blujay API definition, so a change to the files in `src/blujay/` (other than `webhooks.py`, `_errors.py` and `_version.py`) would be overwritten by the next release. If something is wrong or missing, please [open an issue](https://github.com/blujayhq/blujay-python/issues) and we'll fix it at the source. Fixes to the README and examples are welcome as pull requests.

## Working on the library

```sh
pip install build && python -m build     # wheel and sdist in dist/
./smoke/run.sh python                    # installs the wheel and runs the quickstart against a local mock
python tests/custom/test_webhooks.py     # webhook verification tests (with the package installed)
pip install pyright==1.1.414 && python scripts/check_docs.py   # type-checks every README sample and example
```
