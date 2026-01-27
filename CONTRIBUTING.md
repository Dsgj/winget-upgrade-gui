# Contributing to Winget Upgrade Manager

Thank you for your interest in contributing! 🎉

## How to Contribute

### Reporting Bugs

1. Check if the issue already exists in [Issues](../../issues)
2. If not, create a new issue with:
   - Clear description of the problem
   - Steps to reproduce
   - Expected vs actual behavior
   - Windows version and Python version

### Suggesting Features

Open an issue with the `enhancement` label describing:

- What problem it solves
- Proposed solution
- Any alternatives considered

### Submitting Changes

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Test thoroughly
5. Commit with clear messages (`git commit -m 'Add amazing feature'`)
6. Push to your fork (`git push origin feature/amazing-feature`)
7. Open a Pull Request

## Development Setup

```powershell
# Clone your fork
git clone https://github.com/YOUR_USERNAME/winget-upgrade-gui.git
cd winget-upgrade-gui

# Create virtual environment
python -m venv venv
.\venv\Scripts\Activate

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Run the app
python main.py
```

## Code Style

- Follow PEP 8 guidelines
- Use type hints where appropriate
- Add docstrings to functions and classes
- Keep functions focused and concise

## Questions?

Feel free to open an issue for any questions!
