# Security Policy

## Verifying Downloads

All releases include SHA256 checksums generated automatically by GitHub. Click on any release asset to view its checksum.

### Verify with PowerShell

```powershell
(Get-FileHash -Path "WingetUpgradeManager.exe" -Algorithm SHA256).Hash
```

## Why This Project is Safe

- **100% Open Source** — All code is visible and auditable
- **No Telemetry** — Zero data collection
- **No Network Requests** — Only runs local `winget` commands
- **Automated Builds** — Executables built on GitHub's infrastructure
- **Reproducible** — Build the `.exe` yourself from source

## Build from Source

```powershell
git clone https://github.com/YOUR_USERNAME/winget-upgrade-gui.git
cd winget-upgrade-gui
pip install -r requirements.txt -r requirements-dev.txt
python build.py
```

## Reporting Vulnerabilities

Please report security issues privately via GitHub's security advisory feature or email the maintainer directly.
