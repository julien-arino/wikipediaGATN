# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
- Consolidated every Wikipedia/Wikimedia request behind a single shared
  `User-Agent` with a real contact address and the actual package version,
  replacing the placeholder `julien.arino@example.com` and stale-version strings.
- `__version__` is now read from the installed package metadata, so it can no
  longer drift from `pyproject.toml` (previously reported `0.1.1`).
- Replaced emoji/Unicode glyphs in printed messages with ASCII tags to avoid
  `UnicodeEncodeError` on Windows consoles using the cp1252 code page.
- Create the destination directory before writing the cached `ourairports.csv`,
  fixing a first-run `FileNotFoundError` on a fresh data folder.

### Removed
- Dropped the unused `click` runtime dependency.
- Removed the vestigial `setup.py` and the `[tool.setuptools.packages.find]`
  block left over from a setuptools build (the project builds with hatchling).
- Removed the editable `git+ssh://` self-install line from `requirements.txt`,
  which failed for anyone without push access to the repository.

### Documentation
- Added `CITATION.cff` and this changelog.

## [0.1.4]

- Baseline release reviewed for the pyOpenSci / JOSS submission.
