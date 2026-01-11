# Moderne CLI MCP Server

This is an MCP server built using FastMCP that provides tools to interact with the Moderne CLI (`mod`). The Moderne CLI is a command-line tool that enables you to build Lossless Semantic Trees (LSTs) across multiple repositories and run recipes against them from your local machine.

## Features
- AI-driven recipe recommendations based on project goals.
- End-to-end automation for fixing repositories (`analyze`, `build`, `run`, `apply`, `push`).
- Automated documentation generation (`MODERNE_FIX_SUMMARY.md`).
- Integration with Moderne Platform for recipe marketplace and organization management.

## Prerequisites
- **Moderne CLI (`mod`)**: Must be installed and accessible in your PATH. See installation instructions below.
- **Python 3.8+**: Required for this MCP server.
- **OpenAI API Key**: Required for AI-driven recommendations.

## Installation

### Step 1: Download and Install the Moderne CLI

The Moderne CLI can be installed via package managers or manually:

#### Windows (Recommended: Chocolatey)

If you have Chocolatey installed, run:

```powershell
choco install moderne-cli
```

Or download manually from [app.moderne.io](https://app.moderne.io/):

1. Go to [app.moderne.io](https://app.moderne.io/) and sign in.
2. Click the `?` icon in the top right and select your preferred version (Stable or Staging).
3. Download the Windows binary for your OS.
4. Extract and place the `mod` executable in a directory on your PATH (e.g., `C:\Program Files\Moderne` or `%USERPROFILE%\bin`).
5. Verify installation by opening PowerShell and running:

```powershell
mod --version
```

#### macOS (Recommended: Homebrew)

```bash
brew tap moderne-dev/tap
brew install moderne-dev/tap/moderne-cli
```

Or download manually from [app.moderne.io](https://app.moderne.io/).

#### Linux

Download from [app.moderne.io](https://app.moderne.io/) and extract the binary to a directory on your PATH:

```bash
tar -xzf moderne-cli-*.tar.gz
mv mod /usr/local/bin/
chmod +x /usr/local/bin/mod
```

### Step 2: Configure the Moderne CLI

Connect the CLI to the Moderne Platform:

```bash
# Direct the CLI to Moderne
mod config moderne edit https://app.moderne.io

# Authenticate with Moderne (opens web browser)
mod config moderne login

# Sync recipes from the marketplace
mod config recipes moderne sync
```

### Step 3: Set Up This MCP Server

1. Clone or download this repository.
2. Create a `.env` file at the project root with your OpenAI API Key (copy from `.env.example`):

   ```bash
   cp .env.example .env
   # Edit .env and add your OPENAI_API_KEY
   ```

3. Install Python dependencies:

   ```bash
   pip install -r requirements.txt
   ```

4. Run the server:

   ```bash
   python main.py
   ```

## Starting the MCP Server

To start the MCP server with a virtual environment:

```bash
source venv/bin/activate && python3 main.py --help
```

Or if you prefer to run the server without the virtual environment:

```bash
python3 main.py
```

To see available commands and options:

```bash
python main.py --help
```

## Tools

- **`sync_repo`**: Sync a public git repository to your local workspace.
- **`build_lst`**: Build Lossless Semantic Trees (LSTs) for repositories in your workspace.
- **`list_available_recipes`**: Search the Moderne recipe marketplace.
- **`run_recipe`**: Execute a specific recipe on repositories.
- **`ai_recommend_recipes`**: Get AI-powered recipe recommendations based on your goals.
- **`full_automate_fix`**: Orchestrate the entire workflow from sync through build, run, apply, and push.

## Common Workflows

### Running a Recipe

1. **Set up your workspace:**

   ```bash
   mkdir ~/moderne-workspace
   cd ~/moderne-workspace
   ```

2. **Sync repositories from your Moderne organization:**

   ```bash
   mod git sync moderne ~/moderne-workspace "<organization-name>" --with-sources
   ```

3. **Run a recipe:**

   ```bash
   mod run ~/moderne-workspace --recipe <RecipeName>
   ```

4. **Apply and commit changes:**

   ```bash
   mod git apply ~/moderne-workspace --last-recipe-run
   mod git add ~/moderne-workspace --last-recipe-run
   mod git commit ~/moderne-workspace -m "Apply recipe changes" --last-recipe-run
   mod git push ~/moderne-workspace --last-recipe-run
   ```

### Building LSTs Locally

If you have local repositories without pre-built LSTs:

```bash
mod build ~/path/to/workspace
```

### Analyzing Build Results

View build failures and logs in the built-in analytics dashboard:

```bash
mod trace builds analyze "." --last-build
```

## Configuration

For advanced configuration options, see the [Moderne CLI documentation](https://docs.moderne.io/user-documentation/moderne-cli/getting-started/cli-intro).

Common configurations:
- **JDK selection**: `mod config build edit --jdk-distribution temurin --jdk-version 17`
- **Build customization**: `mod config build edit`
- **Auto-completion** (Unix only): `source <(mod generate-completion)`

## Troubleshooting

- **`mod` command not found**: Ensure the Moderne CLI is installed and on your PATH. Restart your terminal after installation.
- **Authentication issues**: Run `mod config moderne login` to refresh your credentials.
- **LST build failures**: Use `mod trace builds analyze "." --last-build` to diagnose and fix issues.

## Resources

- [Moderne CLI Documentation](https://docs.moderne.io/user-documentation/moderne-cli/getting-started/cli-intro)
- [Moderne CLI Workshop](https://docs.moderne.io/user-documentation/moderne-cli/getting-started/moderne-cli-workshop)
- [CLI Reference](https://docs.moderne.io/user-documentation/moderne-cli/cli-reference)
