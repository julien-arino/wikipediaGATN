# pyOpenSci Submission Requirements & Project Status

Based on the [pyOpenSci Author Guide](https://www.pyopensci.org/software-peer-review/how-to/author-guide.html) and the [Editor in Chief Guide](https://www.pyopensci.org/software-peer-review/how-to/editor-in-chief-guide.html), here is a summary of what pyOpenSci requires for software peer review and what is currently missing or needs attention in the `wikipediaGATN` project.

## 1. Core Repository Files
pyOpenSci checks for the presence of several community and documentation files in your repository.

- [x] **`README.md`**: Present. It contains a clear explanation of what the package does and instructions for installation/use.
- [x] **`LICENSE`**: Present (GPLv3). An OSI-approved license is required.
- [x] **`CONTRIBUTING.md`**: Present. It details how to install the package for development and how to contribute to it.
- [x] **`CODE_OF_CONDUCT.md`**: Present. The project has adopted the Contributor Covenant.

## 2. Documentation
pyOpenSci requires sufficient online documentation so reviewers can evaluate the package's function and scope *without installing it*.

- [x] **Online Documentation Site**: Configured via GitHub Pages. Documentation source is in the `docs/` folder.
- **Required Documentation Components**:
  - [x] **User-facing documentation**: Overview of how to install and start using the package.
  - [x] **Quickstart Tutorials**: Short examples of how to use the package and what it can do.
  - [x] **API Documentation**: Detailed documentation for your code's functions, classes, methods, and attributes.

## 3. Automated Tests & Continuous Integration (CI)
- [x] **Automated Tests**: The project has a test suite using `pytest` located in the `tests/` directory.
- [x] **Continuous Integration (CI)**: Configured via GitHub Actions. Tests run automatically on push and pull request.

## 4. Installation & Distribution
- [x] **Standard Import**: The package can be imported into a standard Python environment (`import wikipediaGATN`).
- [ ] **Package Registry**: The package must be installable from a community repository such as PyPI (preferred) and/or a community channel on conda (e.g., conda-forge). You will need to publish the package to PyPI (at least an alpha/beta release) before or during the submission process.

## 5. Scope and Maintenance Commitments
Before submitting, ensure you are aligned with pyOpenSci's expectations:
- [ ] **Maintenance Commitment**: You must plan to maintain the package for at least 1-2 years after the review process is complete.
- [ ] **Point of Contact**: Ensure there is one submitting author who will be the primary, long-term point of contact for pyOpenSci.
- [ ] **Generative AI Disclosure**: Be prepared to disclose the use of Generative AI tools in the development and/or maintenance of the package if applicable.
- [ ] **JOSS Submission (Optional)**: If you plan to submit to the Journal of Open Source Software (JOSS), you can opt into this during the pyOpenSci review. You will need to prepare a `paper.md` following JOSS standards.

## Recommended (Optional but Good Practice)
- [x] **Linting & Formatting**: You are already using `ruff` and `black`, which is recommended.
- [x] **Type Checking**: You have `mypy` in your `pyproject.toml`, which is great.

---

## Action Plan (Next Steps before Submission)
1. **Create missing files**: Add `CONTRIBUTING.md` and `CODE_OF_CONDUCT.md`.
2. **Setup Documentation**: Initialize Sphinx/MkDocs, write user guides, tutorials, and API references, and host them online (e.g., Read the Docs or GitHub Pages).
3. **Configure CI**: Add a GitHub Actions workflow (`.github/workflows/tests.yml`) to run your `pytest` suite automatically.
4. **Publish to PyPI**: Make sure `wikipediaGATN` is published to PyPI so it can be `pip install`ed easily.
5. **Pre-review Survey**: Complete the pyOpenSci [Initial onboarding survey](https://forms.gle/F9mou7S3jhe8DMJ16) (all maintainers should fill this out).
6. **Submit**: Open an issue in the [pyOpenSci/software-review repository](https://github.com/pyOpenSci/software-review/issues) using their submission template.
