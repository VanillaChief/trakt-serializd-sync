# Contributing

Thank you for your interest in contributing to trakt-serializd-sync!

## AI-Assisted Development

This project uses AI tools (GitHub Copilot) to assist with development. We believe in transparency about AI usage:

- AI-generated code sections may include comments like `# AI-generated: ...`
- The [AI-ATTRIBUTION.md](.github/AI-ATTRIBUTION.md) file documents how AI was used
- All contributions (human or AI-assisted) undergo the same review process

## Development Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/VanillaChief/trakt-serializd-sync.git
   cd trakt-serializd-sync
   ```

2. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate
   ```

3. Install in development mode:
   ```bash
   pip install -e ".[dev]"
   ```

4. Run tests:
   ```bash
   pytest
   ```

## Code Style

- Use type hints for all function signatures
- Follow PEP 8 conventions
- Add docstrings for public functions and classes
- Keep functions focused and testable

## Pull Request Process

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Run tests and linting
5. Commit with clear messages
6. Open a pull request

## Reporting Issues

When reporting bugs, please include:
- Python version
- Steps to reproduce
- Expected vs actual behavior
- Relevant log output

## Questions?

Open an issue for any questions about contributing.
