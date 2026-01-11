import os
import subprocess
import json
import logging
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
REPOS_CSV = "/tmp/mcp_repos.csv"
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
        raise Exception(f"Command failed: {result.stderr}")
    return result.stdout

def _sync_repo(repo_url: str, branch: str = "main") -> str:
    os.makedirs(MODERNE_WORKSPACE, exist_ok=True)
    with open(REPOS_CSV, "w") as f:
        f.write("cloneUrl,branch\n")
        f.write(f"{repo_url},{branch}\n")
    output = run_command(["mod", "git", "sync", "csv", "--with-sources", MODERNE_WORKSPACE, REPOS_CSV])
    return f"Successfully synced {repo_url}.\n{output}"

@mcp.tool()
def sync_repo(repo_url: str, branch: str = "main") -> str:
    """Synchronizes a public git repository to the Moderne workspace."""
    return _sync_repo(repo_url, branch)

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
    
    Available Example Recipes:
    {", ".join(common_recipes)}
    
    Return a RAW list of recipe IDs separated by commas, followed by justifications. 
    Example: org.openrewrite.java.dependencies.DependencyVulnerabilityCheck, io.moderne.devcenter.JavaVersionUpgrade
    
    ONLY use recipe IDs that are highly relevant to the goal.
    """
    
    client = get_openai_client()
    if not client:
        return "Error: OPENAI_API_KEY not found in environment."
        
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content

@mcp.tool()
def ai_recommend_recipes(goal: str, project_files: dict) -> str:
    """Uses LLM to analyze project files and suggest appropriate OpenRewrite recipes."""
    return _ai_recommend_recipes(goal, project_files)

def _full_automate_fix(repo_url: str, goal: str, branch_name: str, branch: str = "main") -> dict:
    git_logs = []
    def log_cmd(args, output):
        git_logs.append(f"CMD: {' '.join(args)}\nOUT: {output}")

    try:
        # 1. Sync
        logger.info("Step 1: Syncing repo...")
        sync_out = _sync_repo(repo_url, branch)
        log_cmd(["mod", "git", "sync"], sync_out)
        
        # 2. Build
        logger.info("Step 2: Building LST...")
        build_out = _build_lst()
        log_cmd(["mod", "build"], build_out)
        
        repo_name = repo_url.split("/")[-1].replace(".git", "")
        repo_path = None
        for root, dirs, files in os.walk(MODERNE_WORKSPACE):
            if ".git" in dirs and root.endswith(repo_name):
                repo_path = root
                break
        if not repo_path:
            raise Exception(f"Repo {repo_name} not found in workspace")

        # 3. Analyze
        pom_path = os.path.join(repo_path, "pom.xml")
        pom_content = ""
        if os.path.exists(pom_path):
            with open(pom_path, "r") as f:
                pom_content = f.read()
        
        # 4. Recommendation
        logger.info("Step 3: Getting AI recommendations...")
        ai_resp = _ai_recommend_recipes(goal, {"pom.xml": pom_content})
        log_cmd(["ai_recommend"], ai_resp)
        
        import re
        recipes = re.findall(r"(?:org\.openrewrite|io\.moderne)[\w\.]+", ai_resp)
        if not recipes:
            if "vulnerability" in goal.lower():
                recipes = ["org.openrewrite.java.dependencies.DependencyVulnerabilityCheck"]
            else:
                raise Exception(f"AI failed to find recipes in response: {ai_resp}")

        # 5. Run Recipes
        logger.info(f"Step 4: Running recipes: {recipes}")
        for r_id in recipes:
            run_out = _run_recipe(r_id, options={"maximumUpgradeDelta": "minor", "overrideTransitive": "true"})
            log_cmd(["mod", "run", r_id], run_out)
            
        # 6. Doc gen
        summary_content = f"# Moderne Fix Summary\nGoal: {goal}\nApplied Recipes:\n" + "\n".join([f"- {r}" for r in recipes]) + f"\n\n## AI Analysis\n{ai_resp}"
        with open(os.path.join(repo_path, "MODERNE_FIX_SUMMARY.md"), "w") as f:
            f.write(summary_content)
        
        # 7. Git ops
        logger.info("Step 5: Git operations...")
        def run_git(args):
            res = run_command(args, cwd=repo_path)
            log_cmd(args, res)
            return res

        run_git(["git", "checkout", branch])
        run_git(["git", "pull", "origin", branch])
        run_git(["git", "checkout", "-B", branch_name])
        run_git(["mod", "git", "apply", MODERNE_WORKSPACE, "--last-recipe-run"])
        run_git(["git", "add", "MODERNE_FIX_SUMMARY.md"])
        run_git(["git", "commit", "-am", f"Moderne Auto-Fix: {goal}"])
        run_git(["git", "push", "-u", "origin", branch_name, "--force"])
        
        return {
            "status": "SUCCESS",
            "message": f"Automation completed for {repo_name}.",
            "branch": branch_name,
            "url": f"{repo_url.replace('.git', '')}/tree/{branch_name}",
            "logs": "\n---\n".join(git_logs)
        }

    except Exception as e:
        logger.error(f"Automation failed: {str(e)}")
        return {
            "status": "ERROR",
            "error": str(e),
            "logs": "\n---\n".join(git_logs)
        }

@mcp.tool()
def full_automate_fix_async(repo_url: str, goal: str, branch_name: str, branch: str = "main") -> str:
    """End-to-end automation (Asynchronous)."""
    job_id = str(uuid.uuid4())
    jobs[job_id] = {"status": "PENDING", "type": "full_automate", "repo_url": repo_url}
    thread = threading.Thread(target=background_task, args=(job_id, _full_automate_fix, repo_url, goal, branch_name, branch))
    thread.start()
    return f"Automation started in background. Job ID: {job_id}"

if __name__ == "__main__":
    mcp.run()
