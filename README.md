# 📦 Winget Upgrade Manager

A modern, dark-themed desktop GUI for managing Windows package upgrades via winget.

![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)
![CustomTkinter](https://img.shields.io/badge/CustomTkinter-5.2+-green.svg)
![Windows](https://img.shields.io/badge/Windows-10%2F11-blue.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

<p align="center">
  <strong>Stop using the command line for package updates!</strong><br>
  A beautiful, intuitive interface for Windows Package Manager (winget).
</p>

---

## ✨ Features

- 📋 **Package List View** — See all available updates in a clean card-based layout
- ⬆️ **One-Click Upgrades** — Upgrade individual packages or all at once
- 📊 **Real-Time Progress** — Watch download and installation progress
- 📜 **Live Console** — View command output in the integrated console
- 🌙 **Dark Mode** — Modern dark theme that's easy on the eyes
- 🔄 **Auto-Refresh** — Automatically scan for updates on launch

---

## 📥 Installation

### Option 1: Download Executable (Recommended)

1. Go to [Releases](../../releases)
2. Download the latest `WingetUpgradeManager.exe`
3. Run it — no installation needed!

### Option 2: Run from Source

**Requirements:**

- Windows 10/11
- Python 3.8 or higher
- [winget](https://learn.microsoft.com/en-us/windows/package-manager/winget/) (Windows Package Manager)

```powershell
# Clone the repository
git clone https://github.com/YOUR_USERNAME/winget-upgrade-gui.git
cd winget-upgrade-gui

# Install dependencies
pip install -r requirements.txt

# Run the application
python main.py
```

---

## 🔨 Building from Source

Want to create your own executable? It's easy!

### Quick Build

```powershell
# Install build dependencies
pip install -r requirements-dev.txt

# Run the build script
python build.py
```

The executable will be created at `dist/WingetUpgradeManager.exe`.

### Manual Build with PyInstaller

```powershell
pip install pyinstaller

pyinstaller --onefile --windowed --name WingetUpgradeManager ^
  --collect-all customtkinter ^
  --hidden-import customtkinter ^
  --hidden-import darkdetect ^
  main.py
```

> **Note:** The executable will be approximately 50-80 MB due to the bundled Python runtime and GUI libraries.

---

## 🖥️ Usage

1. **Launch** — The app automatically scans for available updates on startup
2. **Refresh** — Click the 🔄 Refresh button to check for new updates
3. **Upgrade Single** — Click the "Upgrade" button on any package card
4. **Upgrade All** — Click the green "⬆️ Upgrade All" button to upgrade everything

The output console at the bottom shows real-time command output and any errors.

---

## 📁 Project Structure

```
winget-upgrade-gui/
├── main.py              # Application entry point
├── winget_runner.py     # Winget command execution
├── ui_components.py     # Custom UI components
├── build.py             # Local build script
├── requirements.txt     # Runtime dependencies
├── requirements-dev.txt # Build dependencies
├── .github/workflows/   # CI/CD automation
├── SECURITY.md          # Security policy
├── LICENSE              # MIT License
├── CONTRIBUTING.md      # Contribution guidelines
└── README.md            # This file
```

---

## 🔐 Security

This project is a **safe, open-source alternative** to bloatware package managers:

- ✅ **100% Open Source** — All code is visible and auditable
- ✅ **No Telemetry** — Zero data collection
- ✅ **No Network Requests** — Only runs local `winget` commands
- ✅ **Automated CI Builds** — Executables built on GitHub's infrastructure
- ✅ **SHA256 Checksums** — GitHub auto-generates for all releases

See [SECURITY.md](SECURITY.md) for verification instructions.

---

## 🤝 Contributing

Contributions are welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

---

## 📝 License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgments

- [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) — Modern UI library
- [winget](https://github.com/microsoft/winget-cli) — Windows Package Manager
