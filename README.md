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

## Tools
- `sync_repo`: Sync a public git repo.
- `build_lst`: Build LSTs for the workspace.
- `list_available_recipes`: Search the recipe marketplace.
- `run_recipe`: Run a specific recipe.
- `ai_recommend_recipes`: Get recipe suggestions for a goal.
- `full_automate_fix`: Orchestrate the entire fix process from sync to push.
