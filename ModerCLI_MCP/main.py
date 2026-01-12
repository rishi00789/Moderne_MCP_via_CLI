import os
import subprocess
import json
import logging
import re
import threading
import uuid
import time
from typing import List, Optional, Dict
from fastmcp import FastMCP
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# Initialize FastMCP server
mcp = FastMCP("Moderne-CLI-MCP")

# Constants
MODERNE_WORKSPACE = os.getenv("MODERNE_WORKSPACE", "/tmp/moderne-workspace")
RECIPE_CATALOG_PATH = "/tmp/mcp_recipes.json"

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Moderne-CLI-MCP")

# Global Job Tracking
jobs: Dict[str, Dict] = {}

# OpenAI client helper
def get_openai_client():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    return OpenAI(api_key=api_key)

def run_command(cmd: List[str], cwd: str = ".") -> str:
    logger.info(f"Running command: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        error_msg = f"Command '{' '.join(cmd)}' failed with exit code {result.returncode}."
        if result.stderr.strip():
            error_msg += f"\nStderr: {result.stderr.strip()}"
        if result.stdout.strip():
            error_msg += f"\nStdout: {result.stdout.strip()}"
        raise Exception(error_msg)
    return result.stdout

def _sync_repo(repo_url: str, branch: str = "main", force_clean: bool = True, session_id: Optional[str] = None) -> str:
    if force_clean and os.path.exists(MODERNE_WORKSPACE):
        run_command(["rm", "-rf", MODERNE_WORKSPACE])
        
    os.makedirs(MODERNE_WORKSPACE, exist_ok=True)
    temp_csv = f"/tmp/mcp_repos_{session_id or uuid.uuid4()}.csv"
    try:
        with open(temp_csv, "w") as f:
            f.write("cloneUrl,branch\n")
            f.write(f"{repo_url},{branch}\n")
        output = run_command(["mod", "git", "sync", "csv", "--with-sources", MODERNE_WORKSPACE, temp_csv])
        return f"Successfully synced {repo_url}.\n{output}"
    finally:
        if os.path.exists(temp_csv):
            os.remove(temp_csv)

@mcp.tool()
def sync_repo(repo_url: str, branch: str = "main", force_clean: bool = True) -> str:
    """Synchronizes a public git repository to the Moderne workspace."""
    return _sync_repo(repo_url, branch, force_clean)

@mcp.tool()
def clear_workspace() -> str:
    """Wipes the MODERNE_WORKSPACE directory completely."""
    if os.path.exists(MODERNE_WORKSPACE):
        run_command(["rm", "-rf", MODERNE_WORKSPACE])
        return f"Successfully cleared {MODERNE_WORKSPACE}."
    return "Workspace was already empty."

@mcp.tool()
def get_job_status(job_id: str) -> dict:
    """Returns the current status of a background job."""
    if job_id not in jobs:
        return {"error": "Job ID not found"}
    return jobs[job_id]

def background_task(job_id: str, func, *args, **kwargs):
    jobs[job_id]["status"] = "RUNNING"
    try:
        result = func(*args, **kwargs)
        if isinstance(result, dict) and result.get("status") == "ERROR":
            jobs[job_id]["status"] = "FAILED"
            jobs[job_id]["error"] = result.get("error", "Unknown error")
            jobs[job_id]["result"] = result
        else:
            jobs[job_id]["status"] = "COMPLETED"
            jobs[job_id]["result"] = result
    except Exception as e:
        logger.error(f"Job {job_id} failed: {str(e)}")
        jobs[job_id]["status"] = "FAILED"
        jobs[job_id]["error"] = str(e)

def _build_lst() -> str:
    return run_command(["mod", "build", MODERNE_WORKSPACE])

@mcp.tool()
def build_lst_async() -> str:
    """Builds LSTs for the synchronized repositories in the background."""
    job_id = str(uuid.uuid4())
    jobs[job_id] = {"status": "PENDING", "type": "build_lst"}
    thread = threading.Thread(target=background_task, args=(job_id, _build_lst))
    thread.start()
    return f"LST build started in background. Job ID: {job_id}"

def _run_recipe(recipe_id: str, options: Optional[dict] = None) -> str:
    cmd = ["mod", "run", MODERNE_WORKSPACE, "--recipe", recipe_id]
    if options:
        for k, v in options.items():
            cmd.append(f"-P{k}={v}")
    return run_command(cmd)

@mcp.tool()
def run_recipe_async(recipe_id: str, options: Optional[dict] = None) -> str:
    """Runs a specific OpenRewrite recipe in the background."""
    job_id = str(uuid.uuid4())
    jobs[job_id] = {"status": "PENDING", "type": "run_recipe", "recipe_id": recipe_id}
    thread = threading.Thread(target=background_task, args=(job_id, _run_recipe, recipe_id, options))
    thread.start()
    return f"Recipe run {recipe_id} started in background. Job ID: {job_id}"

@mcp.tool()
def list_available_recipes(query: Optional[str] = None) -> str:
    """Lists available OpenRewrite recipes (Synchronous)."""
    if not os.path.exists(RECIPE_CATALOG_PATH):
        run_command(["mod", "config", "recipes", "export", "json", RECIPE_CATALOG_PATH])
    
    with open(RECIPE_CATALOG_PATH, "r") as f:
        recipes = json.load(f)
    
    if query:
        filtered = [r for r in recipes if query.lower() in r.get("id", "").lower() or query.lower() in r.get("description", "").lower()]
    else:
        filtered = recipes[:50]
        
    result = []
    for r in filtered:
        result.append(f"- ID: {r['id']}\n  Description: {r.get('description', 'No description available')[:100]}...")
        
    return "\n".join(result)

def _ai_recommend_recipes(goal: str, project_files: dict) -> str:
    if not os.path.exists(RECIPE_CATALOG_PATH):
        run_command(["mod", "config", "recipes", "export", "json", RECIPE_CATALOG_PATH])
        
    with open(RECIPE_CATALOG_PATH, "r") as f:
        recipes = json.load(f)
        
    common_recipes = [r['id'] for r in recipes[:100]]
    
    prompt = f"""
    Analyze the following project files and suggest the best OpenRewrite recipes to achieve the goal: "{goal}"
    
    Project Files:
    {json.dumps(project_files, indent=2)}
    
    Available Example Recipes (Commonly used):
    {", ".join(common_recipes)}
    
    CRITICAL: 
    1. Prefer standard official recipes starting with 'org.openrewrite' over 'io.moderne.devcenter' templates unless strictly necessary.
    2. MANY recipes require parameters. For the following recipes, YOU MUST use these EXACT keys:
       - 'org.openrewrite.maven.UpgradeParentVersion': MUST use 'groupId', 'artifactId', 'newVersion'
       - 'org.openrewrite.maven.UpgradeDependencyVersion': MUST use 'groupId', 'artifactId', 'newVersion'
       - 'org.openrewrite.maven.ChangePropertyValue': MUST use 'key', 'newValue' (for pom.xml property updates)
       - 'org.openrewrite.java.migrate.UpgradeJavaVersion': MUST use 'version'
    3. You MUST provide the necessary parameters for each recipe in the 'options' field.
    
    Return ONLY a JSON object with the following structure:
    {{
      "recipes": [
        {{
          "id": "org.openrewrite.java.migrate.UpgradeJavaVersion",
          "options": {{ "version": "11" }},
          "justification": "Upgrading to Java 11"
        }},
        ...
      ]
    }}
    """
    
    client = get_openai_client()
    if not client:
        return json.dumps({"recipes": []}) # Fallback empty
        
    response = client.chat.completions.create(
        model="gpt-4o",
        response_format={ "type": "json_object" },
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content

@mcp.tool()
def ai_recommend_recipes(goal: str, project_files: dict) -> str:
    """Uses LLM to analyze project files and suggest appropriate OpenRewrite recipes."""
    return _ai_recommend_recipes(goal, project_files)

def _full_automate_fix(repo_url: str, goal: str, branch_name: str, branch: str = "main", force_clean: bool = False, job_id_internal: Optional[str] = None) -> dict:
    git_logs = []
    def log_cmd(args, output):
        git_logs.append(f"CMD: {' '.join(args)}\nOUT: {output}")

    def update_progress(msg: str):
        if job_id_internal and job_id_internal in jobs:
            jobs[job_id_internal]["progress"] = msg
            logger.info(f"Job {job_id_internal} progress: {msg}")

    try:
        # 1. Sync
        update_progress("Step 1/8: Syncing repository...")
        sync_out = _sync_repo(repo_url, branch, force_clean=force_clean, session_id=job_id_internal)
        log_cmd(["mod", "git", "sync"], sync_out)
        
        repo_name = repo_url.split("/")[-1].replace(".git", "")
        repo_path = None
        for root, dirs, files in os.walk(MODERNE_WORKSPACE):
            if ".git" in dirs and root.endswith(repo_name):
                repo_path = root
                break
        if not repo_path:
            raise Exception(f"Repo {repo_name} not found in workspace")

        def run_mod_git(args):
            # mod git <cmd> [options] <path> [extra_args]
            full_args = ["mod", "git"] + args
            res = run_command(full_args, cwd=MODERNE_WORKSPACE)
            log_cmd(full_args, res)
            return res

        def run_git_raw(args):
            # standard git commands run inside the repo_path
            res = run_command(args, cwd=repo_path)
            log_cmd(args, res)
            return res

        # 2. Checkout and Configure Identity
        update_progress("Step 2/8: Preparing git branch and identity...")
        run_mod_git(["checkout", "-B", repo_path, branch_name])
        # Set local git config to prevent "configured automatically" warnings
        run_git_raw(["git", "config", "user.name", "Moderne Automation"])
        run_git_raw(["git", "config", "user.email", "automation@moderne.io"])
        
        # 3. Build (Indexes the current branch state)
        update_progress("Step 3/8: Building Lossless Semantic Tree (LST)...")
        build_out = _build_lst()
        log_cmd(["mod", "build"], build_out)
        
        # 4. Analyze
        update_progress("Step 4/8: Analyzing project structure...")
        pom_path = os.path.join(repo_path, "pom.xml")
        pom_content = ""
        if os.path.exists(pom_path):
            with open(pom_path, "r") as f:
                pom_content = f.read()
        
        # 5. Recommendation
        update_progress("Step 5/8: Getting AI recipe recommendations...")
        ai_resp_raw = _ai_recommend_recipes(goal, {"pom.xml": pom_content})
        log_cmd(["ai_recommend"], ai_resp_raw)
        
        try:
            ai_data = json.loads(ai_resp_raw)
            ai_recipes = ai_data.get("recipes", [])
        except Exception as e:
            logger.error(f"Failed to parse AI response: {e}")
            ai_recipes = []

        # Mapping common goals to concrete recipes with required parameters
        goal_lower = goal.lower()
        java_version = "11" # Default
        if "java" in goal_lower:
            if "17" in goal_lower: java_version = "17"
            elif "21" in goal_lower: java_version = "21"
            elif "11" in java_version: java_version = "11" # Already set but for clarity

        # Injected safety recipes
        final_recipes = []
        
        # 1. First, check if Java upgrade is needed and not already suggested
        if "java" in goal_lower:
            has_java_upgrade = any("UpgradeJavaVersion" in r["id"] for r in ai_recipes)
            if not has_java_upgrade:
                final_recipes.append({
                    "id": "org.openrewrite.java.migrate.UpgradeJavaVersion",
                    "options": {"version": java_version}
                })
                git_logs.append(f"INJECTED: org.openrewrite.java.migrate.UpgradeJavaVersion with version={java_version}")

        # 2. Add AI recommended recipes
        for r in ai_recipes:
             final_recipes.append(r)

        if not final_recipes:
            raise Exception(f"AI and local logic failed to find recipes. AI raw: {ai_resp_raw}")

        # 6. Run Recipes (Sequentially and Commit locally)
        update_progress(f"Step 6/8: Running {len(final_recipes)} recipes...")
        for i, r_obj in enumerate(final_recipes):
            r_id = r_obj.get("id")
            r_options = r_obj.get("options", {})
            
            # Skip redundant or problematic AI recipes if we already have the primary migrate one
            # (Safety check for redundant java versioning plugins)
            redundant_list = [
                "io.moderne.devcenter.JavaVersionUpgrade", 
                "io.moderne.devcenter.LibraryUpgrade",
                "org.openrewrite.maven.ChangeJavaVersion"
            ]
            has_standard_upgrade = any(rr["id"] == "org.openrewrite.java.migrate.UpgradeJavaVersion" for rr in final_recipes)
            if has_standard_upgrade and r_id in redundant_list:
                 git_logs.append(f"FILTERED: Skipping {r_id} as it is redundant")
                 continue

            update_progress(f"Step 6.{i+1}/{len(final_recipes)}: Running {r_id}...")
            # Merge with global defaults
            options = {"maximumUpgradeDelta": "minor", "overrideTransitive": "true"}
            
            # Normalization Layer: Map AI variations to canonical keys
            norm_options = {}
            for k, v in r_options.items():
                new_k = k
                # 1. Map 'version' -> 'newVersion' for Maven recipes
                if "org.openrewrite.maven" in r_id and k == "version":
                    new_k = "newVersion"
                # 2. Map 'groupIdPattern' -> 'groupId' for upgrades (which don't support patterns)
                if ("UpgradeParentVersion" in r_id or "UpgradeDependencyVersion" in r_id) and k.endswith("Pattern"):
                    new_k = k.replace("Pattern", "")
                norm_options[new_k] = v

            options.update(norm_options)
                
            try:
                run_out = _run_recipe(r_id, options=options)
                log_cmd(["mod", "run", r_id], run_out)
            except Exception as run_err:
                error_summary = str(run_err).split("\n")[0]
                msg = f"FAILED RUN: {r_id} execution failed."
                logger.warning(f"{msg} Error: {error_summary}")
                git_logs.append(f"FAILED RUN: {r_id} ({error_summary})")
                continue
            
            # Extract specific Run ID from output
            run_id = None
            # Check for fix results path
            run_id_match = re.search(r"/run/([A-Za-z0-9-]+)/fix\.patch", run_out)
            if not run_id_match:
                # Might be search result or just no changes
                if "search.patch" in run_out:
                    git_logs.append(f"SKIPPED: {r_id} produced SEARCH results only")
                else:
                    git_logs.append(f"SKIPPED: {r_id} produced no code changes")
                continue
                
            run_id = run_id_match.group(1)
            
            # Hybrid Staging: Use mod git apply with EXPLICIT Run ID
            if run_id:
                # 1. Apply patch to disk using explicit Run ID
                apply_out = run_mod_git(["apply", "--recipe-run", run_id, repo_path])
                
                # Double check CLI reported success
                if "Applied patches to 0 repositories" in apply_out:
                    git_logs.append(f"SKIPPED APPLY: CLI reports 0 repositories updated for {r_id}")
                    continue

                # 2. Stage only source changes (exclude artifacts)
                run_git_raw(["git", "add", "-A", "--", ".", ":(exclude)target/", ":(exclude).idea/", ":(exclude).vscode/", ":(exclude).moderne/"])
                
                # 3. Check if there are actually any changes staged
                has_changes = False
                try:
                    run_command(["git", "diff-index", "--quiet", "HEAD", "--"], cwd=repo_path)
                    has_changes = False
                except Exception:
                    has_changes = True

                if has_changes:
                    # 4. Commit locally
                    run_git_raw(["git", "commit", "-m", f"Moderne Auto-Fix: Applied {r_id}"])
                    git_logs.append(f"APPLIED AND COMMITTED: {r_id} (Run {run_id})")
                    
                    # 5. REBUILD LST: Critical for cumulative changes!
                    try:
                        update_progress(f"Step 6.{i+1}.refresh: Refreshing LST after {r_id}...")
                        build_out = _build_lst()
                        log_cmd(["mod", "build (refresh)"], build_out)
                    except Exception as build_err:
                        error_summary = str(build_err).split("\n")[0]
                        msg = f"ROLLBACK: {r_id} broke the build. Reverting changes."
                        logger.warning(f"{msg} Error: {error_summary}")
                        git_logs.append(f"FAILED BUILD: {msg} ({error_summary})")
                        # Revert last commit
                        run_git_raw(["git", "reset", "--hard", "HEAD~1"])
                        continue
                else:
                    git_logs.append(f"SKIPPED COMMIT: No net changes for {r_id}")
            
        # 7. Doc gen
        update_progress("Step 7/8: Generating fix summary documentation...")
        summary_content = f"# Moderne Fix Summary\nGoal: {goal}\nApplied Recipes:\n" + "\n".join([f"- {r['id']}" for r in final_recipes]) + f"\n\n## AI Analysis\n{ai_resp_raw}"
        summary_path = os.path.join(repo_path, "MODERNE_FIX_SUMMARY.md")
        with open(summary_path, "w") as f:
            f.write(summary_content)
        
        # 8. Final Push (All changes at once)
        update_progress("Step 8/8: Finalizing and pushing all changes...")
        if os.path.exists(summary_path):
            run_git_raw(["git", "add", "MODERNE_FIX_SUMMARY.md"])
            # Always commit summary if it exists
            run_git_raw(["git", "commit", "-m", "Moderne Auto-Fix: Added summary documentation"])
            
        # Push everything to origin once
        run_git_raw(["git", "push", "origin", branch_name])
        git_logs.append(f"PUSHED ALL CHANGES TO {branch_name}")
        
        update_progress("Completed successfully")
        
        return {
            "status": "SUCCESS",
            "message": f"Automation completed for {repo_name}.",
            "branch": branch_name,
            "url": f"{repo_url.replace('.git', '')}/tree/{branch_name}",
            "logs": "\n---\n".join(git_logs)
        }

    except Exception as e:
        logger.error(f"Automation failed: {str(e)}")
        # If the logs don't include the specific failure command, append the exception message
        error_log = str(e)
        if not any(error_log in log for log in git_logs):
            git_logs.append(f"FAILURE:\n{error_log}")
            
        return {
            "status": "ERROR",
            "error": str(e),
            "logs": "\n---\n".join(git_logs)
        }

@mcp.tool()
def full_automate_fix_async(repo_url: str, goal: str, branch_name: str, branch: str = "main", force_clean: bool = True) -> str:
    """End-to-end automation (Asynchronous)."""
    job_id = str(uuid.uuid4())
    jobs[job_id] = {"status": "PENDING", "type": "full_automate", "repo_url": repo_url, "progress": "Initializing..."}
    thread = threading.Thread(target=background_task, args=(job_id, _full_automate_fix, repo_url, goal, branch_name, branch), kwargs={"force_clean": force_clean, "job_id_internal": job_id})
    thread.start()
    return f"Automation started in background. Job ID: {job_id}"

if __name__ == "__main__":
    mcp.run()
