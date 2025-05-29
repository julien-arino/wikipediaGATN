# wikipediaGATN

Python package that grabs the global air transportation network from wikipedia airport pages.

## Setting up

If using a virtual environment
```bash
source /path/to/venv/bin/activate
```

If running before deploying the package, you need to run stuff from the top directory in the repo. Set

```
export PYTHONPATH=src
```

and then call the code using, e.g.,

```
python -m examples.grab_info_from_IATA
```

Note the nonstandard call: `-m`, `.` instead of `/` to indicate a subdirectory and no `.py` extension.

## Example uses

