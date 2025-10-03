# Pre-commit Hooks Setup

This project uses pre-commit hooks to ensure code quality before commits are allowed.

## What Gets Checked

Before every commit, the following checks run automatically:

1. **Ruff Linter** - Checks Python code for errors and style issues
2. **Ruff Formatter** - Formats Python code consistently
3. **Trailing Whitespace** - Removes trailing whitespace
4. **End of File** - Ensures files end with a newline
5. **YAML Validation** - Checks YAML syntax
6. **Large Files** - Prevents accidentally committing large files
7. **Merge Conflicts** - Detects unresolved merge conflict markers
8. **Unit Tests** - Runs all unit tests to ensure nothing is broken

## Installation

Pre-commit hooks are automatically installed when you run:

```bash
uv run pre-commit install
```

This is done automatically during project setup, but if you need to reinstall:

```bash
# Reinstall hooks
uv run pre-commit install

# Uninstall hooks
uv run pre-commit uninstall
```

## Usage

### Automatic (Recommended)

Once installed, hooks run automatically on `git commit`. If any check fails, the commit is blocked.

```bash
git add .
git commit -m "Your message"
# Hooks run automatically
# If they fail, fix issues and try again
```

### Manual Run

Run hooks on all files without committing:

```bash
# Run all hooks on all files
uv run pre-commit run --all-files

# Run specific hook
uv run pre-commit run ruff --all-files
uv run pre-commit run pytest-unit --all-files
```

### Skip Hooks (Not Recommended)

Only use this for emergency commits:

```bash
git commit --no-verify -m "Emergency fix"
```

## What Happens When Checks Fail

### Linting/Formatting Failures

If ruff finds issues, it will automatically fix them:

```bash
$ git commit -m "Add feature"
ruff.....................................................................Failed
- hook id: ruff
- files were modified by this hook

# Files are automatically fixed
# Stage the fixes and commit again
$ git add .
$ git commit -m "Add feature"
```

### Test Failures

If unit tests fail, you must fix them before committing:

```bash
$ git commit -m "Add feature"
pytest unit tests........................................................Failed
- hook id: pytest-unit
- exit code: 1

FAILED tests/unit/test_api.py::test_health - AssertionError

# Fix the failing test
# Then try again
$ git commit -m "Add feature"
```

## CI/CD Integration

The same checks run in CI/CD:

- **Linting**: `.github/workflows/lint.yml`
- **Unit Tests**: `.github/workflows/test.yml` (unit tests)
- **Integration Tests**: `.github/workflows/test.yml` (fast integration tests only)

### Slow Tests

Some integration tests are marked as `@pytest.mark.slow` and are skipped in CI:

```python
@pytest.mark.slow
def test_long_running_operation():
    # This test is skipped in CI
    pass
```

Run slow tests manually:

```bash
# Run only slow tests
uv run pytest -m slow

# Run all tests including slow
uv run pytest
```

## Troubleshooting

### Hooks Not Running

```bash
# Check if hooks are installed
ls -la .git/hooks/pre-commit

# Reinstall
uv run pre-commit install
```

### Hooks Taking Too Long

Unit tests run on every commit. If they're too slow:

```bash
# Skip hooks for this commit only
git commit --no-verify -m "WIP"

# Or run tests manually before committing
uv run pytest tests/unit/
git commit -m "Feature complete"
```

### Update Hook Versions

```bash
# Update to latest hook versions
uv run pre-commit autoupdate

# Commit the updated config
git add .pre-commit-config.yaml
git commit -m "Update pre-commit hooks"
```

## Configuration

Edit `.pre-commit-config.yaml` to customize:

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.8.4
    hooks:
      - id: ruff
        args: [--fix]  # Customize args here
```

## Best Practices

1. **Run hooks before pushing**: `uv run pre-commit run --all-files`
2. **Keep tests fast**: Unit tests should complete in < 30 seconds
3. **Don't skip hooks**: They catch issues early
4. **Update regularly**: `uv run pre-commit autoupdate`
5. **Fix issues immediately**: Don't accumulate technical debt

## Why Pre-commit Hooks?

- **Catch issues early**: Before they reach CI/CD
- **Consistent code style**: Automatic formatting
- **Prevent broken commits**: Tests must pass
- **Save CI time**: Fewer failed builds
- **Better code quality**: Enforced standards

## Related Documentation

- [Pre-commit Documentation](https://pre-commit.com/)
- [Ruff Documentation](https://docs.astral.sh/ruff/)
- [Pytest Documentation](https://docs.pytest.org/)
