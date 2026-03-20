# ProjectRock

ProjectRock is a hardened WordPress discovery & scanning tool compiled into a single Windows executable.

## ✅ What’s Included

- ✅ WordPress URL discovery + verification
- ✅ Anonymity via TOR/Proxies
- ✅ Secure HTTP handling (SSL verification enforced)
- ✅ Safe logging with credential redaction
- ✅ Multi-threaded scanning engine
- ✅ Standalone Windows executable: `dist\projectrock.exe`

## 🛠️ Build an Executable (Windows)

1. Open PowerShell in this folder.
2. Run:
   ```powershell
   .\build_projectrock.bat
   ```
3. Resulting executable will be at:
   - `dist\projectrock.exe`

## ▶️ Run (Windows)

- To run directly from the source:
  ```powershell
  python unified_scanner.py
  ```

- To run the bundled executable:
  ```powershell
  dist\projectrock.exe
  ```

## 🧩 Notes

- All code changes must be rebuilt into `projectrock.exe` to take effect.
- Configuration is centralized in `config.py`.
- Logs are stored in `%USERPROFILE%\.projectrock\logs` by default.

