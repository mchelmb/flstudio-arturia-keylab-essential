# Development Environment

The repository uses a project-local `.venv` for editor tooling. It is deliberately separate from
the Python interpreter embedded in FL Studio.

## Setup

From PowerShell in the repository root:

```powershell
.\setup-dev.ps1
```

The setup selects Python 3.12 and installs:

- the runtime-side development dependency from `requirements.txt`;
- `fl-studio-api-stubs==37.0.1`, which provides editor documentation and static analysis for
  FL Studio's built-in modules.

The stubs live inside `.venv`; they are not copied into the script folder and cannot shadow FL
Studio's modules at runtime. The deployment script continues to copy only the script files and
`vst_maps`.

In VS Code, select `.venv` using **Python: Select Interpreter**. `pyrightconfig.json` also points
Pyright at the same environment and restricts analysis to the root script files.

## Limitations

The API stub package is a development aid, not an FL Studio runtime. Its declarations may lag the
version embedded in FL Studio, so behavior must still be verified in the DAW. Genuine project type
errors remain visible; the stubs only supply the host API surface.