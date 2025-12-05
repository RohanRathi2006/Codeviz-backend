import os
import shutil
import uuid
from git import Repo

# We will save repos in a folder called 'temp_repos'
BASE_TEMP_DIR = "temp_repos"

# CORRECTION: This function should only take ONE argument (the URL)
def clone_repository(github_url: str):
    """
    Clones a GitHub repo into a unique temporary folder.
    Returns the path to that folder.
    """
    # 1. Generate a unique folder name automatically
    session_id = str(uuid.uuid4())
    repo_path = os.path.join(BASE_TEMP_DIR, session_id)
    
    print(f"   [Service] Cloning {github_url} into {repo_path}...")
    
    try:
        # 2. Perform the clone
        Repo.clone_from(github_url, repo_path)
        return repo_path
    except Exception as e:
        raise Exception(f"Failed to clone repository: {str(e)}")

def delete_repository(repo_path: str):
    """
    Deletes the temporary folder to free up space.
    """
    if os.path.exists(repo_path):
        # rmtree deletes a directory and all its contents
        try:
            # Change permission for read-only files (common git issue on Windows)
            for root, dirs, files in os.walk(repo_path):
                for d in dirs:
                    os.chmod(os.path.join(root, d), 0o777)
                for f in files:
                    os.chmod(os.path.join(root, f), 0o777)
            
            shutil.rmtree(repo_path)
            print(f"   [Service] Deleted {repo_path}")
        except Exception as e:
            print(f"   [Warning] Could not fully delete {repo_path}: {e}")