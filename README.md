# Moderne CLI MCP Server

This is an MCP server built using FastMCP that provides tools to interact with the Moderne CLI (`mod`).

## Features
- AI-driven recipe recommendations based on project goals.
- End-to-end automation for fixing repositories (`analyze`, `build`, `run`, `apply`, `push`).
- Automated documentation generation (`MODERNE_FIX_SUMMARY.md`).

## Setup
1. Create a `.env` file with your `OPENAI_API_KEY`.
2. Install dependencies: `pip install -r requirements.txt`.
3. Run the server: `python main.py`.

## Install on Windows

Follow these steps to install and run the Moderne CLI on Windows:

1. Install Python 3.8+ from the Microsoft Store or https://www.python.org and ensure `python` and `pip` are on your PATH.
2. (Optional) Create a virtual environment and activate it:

	- PowerShell (recommended):

	  ```powershell
	  python -m venv .venv
	  .\.venv\Scripts\Activate.ps1
	  ```

	- Command Prompt:

	  ```cmd
	  python -m venv .venv
	  .\.venv\Scripts\activate.bat
	  ```

3. Install dependencies:

	```powershell
	pip install -r requirements.txt
	```

4. Create a `.env` file at the project root with your `OPENAI_API_KEY` (you can copy `.env.example`):

	```powershell
	copy .env.example .env
	# then edit .env with your API key
	notepad .env
	```

5. Run the server:

	```powershell
	python main.py
	```

Notes:
- If you encounter execution policy errors when running the PowerShell activation script, run PowerShell as Administrator and allow script execution for the current user:

  ```powershell
  Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
  ```

- If you prefer to install system-wide, run `pip install -r requirements.txt` without a virtual environment. Use an elevated shell if necessary.


## Tools
- `sync_repo`: Sync a public git repo.
- `build_lst`: Build LSTs for the workspace.
- `list_available_recipes`: Search the recipe marketplace.
- `run_recipe`: Run a specific recipe.
- `ai_recommend_recipes`: Get recipe suggestions for a goal.
- `full_automate_fix`: Orchestrate the entire fix process from sync to push.
