# Static assets

This directory holds custom static files (CSS, images, JavaScript) for the Sphinx
documentation. It is referenced by `html_static_path = ["_static"]` in `docs/conf.py`.
It is intentionally tracked (even when otherwise empty) so the Sphinx build does not
warn that the static path is missing.
