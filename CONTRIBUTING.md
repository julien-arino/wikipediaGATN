# Contributing to wikipediaGATN

Thank you for your interest in contributing to `wikipediaGATN`! We welcome contributions in the form of bug reports, feature requests, documentation improvements, and code changes.

## Development Setup

To set up a local development environment:

1. **Clone the repository**:
   ```bash
   git clone https://github.com/julien-arino/wikipediaGATN.git

   cd wikipediaGATN
   ```

2. **Create a virtual environment**:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install the package in editable mode with development dependencies**:
   ```bash
   pip install -e ".[dev]"
   ```

4. **Download the required spaCy model**:
   ```bash
   python -m spacy download en_core_web_sm
   ```

## Running Tests

We use `pytest` for testing. To run the full test suite:

```bash
pytest
```

To run only the tests that do not require an active internet connection (recommended for rapid development):

```bash
pytest -m "not network"
```

## Pull Request Workflow

1. **Create a branch** for your changes:
   ```bash
   git checkout -b feature/your-feature-name
   ```
2. **Implement your changes** and add tests if applicable.
3. **Ensure tests pass** and code follows the project's style (we use `ruff` and `black`).
4. **Push your branch** to GitHub.
5. **Open a Pull Request** against the `main` branch.

## Code of Conduct

By participating in this project, you agree to abide by the [Code of Conduct](CODE_OF_CONDUCT.md).
