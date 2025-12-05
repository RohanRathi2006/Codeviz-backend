from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from services.file_service import clone_repository, delete_repository
from services.parser_service import parse_repo
from fastapi.middleware.cors import CORSMiddleware
import traceback
import os
import google.generativeai as genai

app = FastAPI()

# --- CONFIGURATION ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# YOUR API KEY
GOOGLE_API_KEY = "AIzaSyCponxtZA9atROZU5ejs5tZdRD5SXJUJAI"

# --- REQUEST MODELS ---
class RepoRequest(BaseModel):
    url: str

class ContentRequest(BaseModel):
    path: str
    url: str 

class ExplainRequest(BaseModel):
    code: str

# --- GLOBAL STATE ---
current_repo_path = None 

# --- HELPER: SMART MODEL SELECTOR ---
def get_working_model():
    """
    Dynamically finds a working model name to prevent 404 errors.
    Prioritizes 1.5-Flash, then Pro, then fallback.
    """
    try:
        genai.configure(api_key=GOOGLE_API_KEY)
        
        # 1. Ask Google what models are available to THIS key
        available_models = []
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                available_models.append(m.name)
        
        # 2. Pick the best one
        # Preference order: 1.5 Flash -> 1.5 Pro -> Pro -> Any
        for model in available_models:
            if "gemini-1.5-flash" in model: return model
        
        for model in available_models:
            if "gemini-1.5-pro" in model: return model
            
        for model in available_models:
            if "gemini-pro" in model: return model
            
        # 3. Fallback: Just take the first one found
        if available_models:
            return available_models[0]
            
        return "gemini-pro" # Absolute backup
        
    except Exception as e:
        print(f"Model selection error: {e}")
        return "gemini-pro"

# --- ENDPOINTS ---

@app.get("/")
def health_check():
    return {"status": "Backend is running"}

@app.post("/visualize")
async def visualize_repo(request: RepoRequest):
    global current_repo_path
    repo_path = None
    try:
        # Cleanup previous session
        if current_repo_path and os.path.exists(current_repo_path):
            try:
                delete_repository(current_repo_path)
            except:
                pass 

        print(f"--- STARTING PROCESS for {request.url} ---")
        
        # Clone and Parse
        repo_path = clone_repository(request.url)
        current_repo_path = repo_path 
        graph_data = parse_repo(repo_path)
        
        return graph_data
        
    except Exception as e:
        print("\n!!!!!!!!!!!!!! ERROR OCCURRED !!!!!!!!!!!!!!")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/content")
async def get_content(request: ContentRequest):
    global current_repo_path
    if not current_repo_path:
        raise HTTPException(status_code=400, detail="No repository loaded.")
    
    full_path = os.path.join(current_repo_path, request.path)
    if not os.path.exists(full_path):
        raise HTTPException(status_code=404, detail=f"File not found: {request.path}")
        
    try:
        with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
            return {"code": f.read()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading file: {str(e)}")

@app.post("/explain")
async def explain_code(request: ExplainRequest):
    """
    Sends code to Google Gemini AI for an explanation.
    """
    try:
        # 1. Force Configuration
        genai.configure(api_key=GOOGLE_API_KEY)

        # 2. Limit text length
        code_snippet = request.code[:2000] 
        
        # 3. SMART SELECTION (The Fix)
        model_name = get_working_model()
        print(f"Using AI Model: {model_name}") # This prints to your terminal so you know which one worked
        
        model = genai.GenerativeModel(model_name)
        
        prompt = f"You are a Senior Software Architect. Explain this code file briefly in 3 clear bullet points. Focus on its role in the system architecture:\n\n{code_snippet}"
        
        response = model.generate_content(prompt)
        
        return {"explanation": response.text}
        
    except Exception as e:
        print(f"AI Error: {e}")
        return {"explanation": f"AI Error: {str(e)}"}