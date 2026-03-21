# CrowdStrike Exclusion Request — AutoDocumentator

**Date:** March 20, 2026
**Requested By:** [YOUR NAME]
**Department:** [YOUR DEPARTMENT]
**Priority:** Standard

---

## Summary

Requesting a CrowdStrike Falcon sensor exclusion and code signing for **AutoDocumentator**, an internally developed SOP documentation tool. CrowdStrike is terminating the process due to behavioral detections triggered by the application's legitimate recording functionality.

---

## Application Details

| Field | Value |
|-------|-------|
| **Application Name** | AutoDocumentator |
| **Version** | 1.0.0 |
| **Publisher** | Segra (internal tool) |
| **Runtime** | Python 3.13, packaged as standalone Windows EXE via PyInstaller |
| **Install Path** | `[DEPLOYMENT_PATH]\AutoDocumentator\AutoDocumentator.exe` |
| **Network Access** | Outbound HTTPS only — Azure OpenAI endpoint, Microsoft Graph API |
| **Requires Admin** | No |
| **User Data** | Screenshots and settings stored locally in `output\` folder next to the EXE |

---

## Purpose

AutoDocumentator is an internal tool that records a user's on-screen actions (mouse clicks, keyboard input, screenshots) and compiles them into step-by-step Standard Operating Procedure (SOP) documents. It integrates with Segra's M365 Copilot (Azure OpenAI) to generate professional documentation in HTML, Markdown, and Word formats.

**Business justification:** Replaces manual SOP creation. Users press Record, perform the procedure they want to document, press Stop, and the tool generates the documentation automatically with annotated screenshots.

---

## Why CrowdStrike Flags It

The application's core functionality requires Windows APIs that are also used by keyloggers and screen capture malware. The following behavioral detections are expected and legitimate:

| API / Behavior | Why the App Uses It | What CrowdStrike Sees |
|----------------|--------------------|-----------------------|
| `SetWindowsHookEx(WH_KEYBOARD_LL)` | Records keyboard input during SOP capture to document typed text and shortcuts | Keylogger hook installation |
| `SetWindowsHookEx(WH_MOUSE_LL)` | Records mouse clicks to identify which UI elements were interacted with | Mouse surveillance hook |
| `BitBlt` / `CreateCompatibleDC` (via `mss` library) | Captures screenshots at each click to include annotated images in the SOP | Screen capture / scraping |
| `GetForegroundWindow` + `GetWindowThreadProcessId` | Identifies which application window the user is working in, to label each step (e.g., "In Google Chrome") | Process enumeration / surveillance |
| `win32crypt.CryptProtectData` | Encrypts stored API keys using DPAPI | Credential manipulation (false positive) |

**None of these APIs are used for unauthorized data collection.** All captured data stays local on the user's machine unless they explicitly export or run AI analysis.

---

## Security Controls Already Implemented

The application has undergone two security audits with 27 vulnerabilities identified and patched:

- **No data exfiltration** — All recordings are stored locally. AI analysis is opt-in and uses Segra's Azure OpenAI endpoint only.
- **DPAPI credential encryption** — API keys encrypted at rest using Windows DPAPI, tied to the user account.
- **MSAL authentication** — Entra ID delegated auth with minimal scopes (`Files.Read`, `Sites.Read.All`).
- **Permission-trimmed results** — Graph Search results are scoped to the authenticated user's permissions.
- **XSS prevention** — HTML output uses Jinja2 autoescape and full 5-character HTML escaping.
- **Prompt injection mitigation** — User input is sanitized before embedding in AI prompts.
- **Atomic file writes** — Settings written atomically to prevent corruption.
- **Token cache permissions** — MSAL token cache restricted to owner-only access via `icacls`.
- **No sensitive data in logs** — Error messages, dry-run output, and Graph error handlers never log tokens, API keys, or response bodies.

Full audit report available at: `SECURITY_AUDIT.md` in the project repository.

---

## Requested Actions

### 1. CrowdStrike Falcon Sensor Exclusion

**Option A — Process path exclusion (recommended):**
- **Exclusion type:** Process
- **Path pattern:** `*\AutoDocumentator\AutoDocumentator.exe`
- **Apply to:** [SPECIFY HOST GROUPS OR ALL]

**Option B — Hash-based exclusion:**
- Run the following on the deployed EXE to get the SHA256:
  ```powershell
  Get-FileHash "C:\Path\To\AutoDocumentator\AutoDocumentator.exe" -Algorithm SHA256
  ```
- Add the resulting hash as an allowed indicator in Falcon console.

**Option C — Machine Learning exclusion (if ML-based detection):**
- Falcon Console → Configuration → Prevention Policies
- Add the path to the ML exclusion list

### 2. Code Signing (Recommended)

Sign the EXE with Segra's code signing certificate to establish publisher trust:

```powershell
# Using signtool from Windows SDK
signtool sign /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 /f "\\path\to\segra-cert.pfx" /p "CERTIFICATE_PASSWORD" "C:\Path\To\AutoDocumentator\AutoDocumentator.exe"

# Verify the signature
signtool verify /pa "C:\Path\To\AutoDocumentator\AutoDocumentator.exe"
```

If Segra uses Azure Trusted Signing or an HSM-based certificate, adjust the signing command accordingly.

---

## Risk Assessment

| Risk | Mitigation |
|------|-----------|
| Tool could be misused for unauthorized keylogging | Recording only runs when user explicitly clicks "Start Recording"; visible overlay with blinking indicator shown during recording; recording stops on window close |
| Captured data could contain sensitive information | All data stored locally; user controls what to record and export; AI analysis is opt-in |
| Exclusion could be exploited by malware impersonating the app | Use hash-based exclusion (Option B) rather than path-based to prevent impersonation; code signing provides additional verification |

---

## Contact

For questions about the application's functionality, security posture, or source code access:

- **Developer:** [YOUR NAME]
- **Email:** [YOUR EMAIL]
- **Repository:** [REPO URL IF APPLICABLE]
