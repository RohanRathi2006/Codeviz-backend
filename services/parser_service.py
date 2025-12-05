import os
import ast
import re
import networkx as nx
from git import Repo

def get_directory_structure(rootdir):
    """
    Recursively builds a JSON tree of the directory structure.
    Sorts folders first, then files. Ignores hidden files like .git.
    """
    dir_name = os.path.basename(rootdir)
    structure = {"name": dir_name, "type": "folder", "children": []}

    try:
        # Get list of items and sort them (Directories first, then Files)
        items = os.listdir(rootdir)
        items.sort(key=lambda x: (not os.path.isdir(os.path.join(rootdir, x)), x.lower()))

        for item in items:
            if item.startswith('.'): # Skip hidden files (.git, .vscode)
                continue
            
            full_path = os.path.join(rootdir, item)
            
            if os.path.isdir(full_path):
                structure["children"].append(get_directory_structure(full_path))
            else:
                structure["children"].append({"name": item, "type": "file"})
    except PermissionError:
        pass # Skip folders we can't read

    return structure

def parse_repo(repo_path: str):
    nodes = []
    edges = []
    file_map = set()
    
    # 1. ANALYZE GIT HISTORY (Hotspot Detection)
    commit_counts = {}
    try:
        repo = Repo(repo_path)
        for blob in repo.head.commit.tree.traverse():
            if blob.type == 'blob': 
                try:
                    commits = list(repo.iter_commits(paths=blob.path, max_count=50))
                    commit_counts[blob.path] = len(commits)
                except:
                    commit_counts[blob.path] = 0
    except Exception as e:
        print(f"Git analysis failed: {e}")

    # 2. Map files & Attach Metadata
    for root, _, files in os.walk(repo_path):
        for file in files:
            if file.endswith((".py", ".java", ".js", ".jsx", ".ts", ".tsx")):
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, repo_path).replace("\\", "/")
                
                loc = 0
                try:
                    with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                        loc = sum(1 for _ in f)
                except: pass

                churn = commit_counts.get(rel_path, 0)

                file_map.add(rel_path)
                nodes.append({
                    "id": rel_path,
                    "label": file,
                    "data": { "loc": loc, "churn": churn }
                })

    # 3. Analyze Imports
    for node in nodes:
        file_path = node["id"]
        full_path = os.path.join(repo_path, file_path)
        try:
            with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
                if file_path.endswith(".py"):
                    try:
                        tree = ast.parse(content)
                        for ast_node in ast.walk(tree):
                            imported = None
                            if isinstance(ast_node, ast.Import):
                                for alias in ast_node.names: imported = alias.name
                            elif isinstance(ast_node, ast.ImportFrom):
                                if ast_node.module: imported = ast_node.module
                            if imported:
                                target = imported.replace(".", "/") + ".py"
                                create_edge(file_path, target, file_map, edges)
                    except: pass
                elif file_path.endswith(".java"):
                    imports = re.findall(r'import\s+([\w\.]+);', content)
                    for imp in imports:
                        target = imp.split(".")[-1] + ".java"
                        create_edge(file_path, target, file_map, edges)
                elif file_path.endswith((".js", ".jsx", ".ts", ".tsx")):
                     js_imports = re.findall(r'(?:import\s+.*?from\s+[\'"](.*?)[\'"])|(?:require\([\'"](.*?)[\'"]\))', content)
                     for match in js_imports:
                        imp = match[0] or match[1]
                        if imp:
                            clean_imp = imp.split("/")[-1].replace(".js", "").replace(".ts", "")
                            create_edge(file_path, clean_imp, file_map, edges)
        except: pass

    # 4. Cycle Detection
    G = nx.DiGraph()
    for edge in edges: G.add_edge(edge["source"], edge["target"])
    cycles = list(nx.simple_cycles(G))
    cyclic_edges = set()
    for cycle in cycles:
        for i in range(len(cycle)):
            cyclic_edges.add(f"{cycle[i]}-{cycle[(i + 1) % len(cycle)]}")

    for edge in edges:
        edge["isCyclic"] = f"{edge['source']}-{edge['target']}" in cyclic_edges

    # 5. NEW: GENERATE DIRECTORY TREE
    directory_tree = get_directory_structure(repo_path)

    return {"nodes": nodes, "edges": edges, "tree": directory_tree} # Added tree

def create_edge(source, target_suffix, file_map, edges):
    for known_file in file_map:
        if known_file.endswith(target_suffix) or (target_suffix in known_file and known_file.split("/")[-1].startswith(target_suffix)):
            if source != known_file:
                edges.append({"id": f"{source}-{known_file}", "source": source, "target": known_file, "isCyclic": False})
                break