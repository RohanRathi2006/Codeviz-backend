from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from services.file_service import clone_repository, delete_repository
from services.parser_service import parse_repo
from fastapi.middleware.cors import CORSMiddleware
import traceback
import os
import hashlib # NEW: For caching results
import google.generativeai as genai
from dotenv import load_dotenv 

# 1. Load Environment Variables
load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 2. Get Key Securely
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# --- CACHE STORAGE (Saves money and time) ---
explanation_cache = {} 

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

# --- ENDPOINTS ---

@app.get("/")
def health_check():
    return {"status": "Backend is running"}

@app.post("/visualize")
async def visualize_repo(request: RepoRequest):
    global current_repo_path
    repo_path = None
    try:
        # Clear cache when loading a new repo to save memory
        explanation_cache.clear()
        
        if current_repo_path and os.path.exists(current_repo_path):
            try:
                delete_repository(current_repo_path)
            except:
                pass 

        print(f"--- STARTING PROCESS for {request.url} ---")
        
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
    Ultimate AI Handler:
    1. Checks Cache (Instant result if already asked)
    2. Rotates Models (Lite -> Latest -> Pro) to bypass limits
    """
    if not GOOGLE_API_KEY:
        return {"explanation": "⚠️ Server Error: API Key not configured. Check .env file."}

    # 1. CACHE CHECK (Zero Quota Usage)
    # Create a unique ID for this code snippet
    code_hash = hashlib.md5(request.code.encode()).hexdigest()
    if code_hash in explanation_cache:
        print("⚡ Serving from Cache (Fast!)")
        return {"explanation": explanation_cache[code_hash]}

    try:
        genai.configure(api_key=GOOGLE_API_KEY)
        code_snippet = request.code[:2000] 
        prompt = f"You are a Senior Software Architect. Explain this code file briefly in 3 clear bullet points. Focus on its role in the system architecture:\n\n{code_snippet}"

        # 2. MODEL ROTATION LIST
        # If one is busy, we try the next one immediately.
        models_to_try = [
            "gemini-2.0-flash-lite",  # Try Lite first (Fastest)
            "gemini-flash-latest",    # Fallback to Flash
            "gemini-pro"              # Last resort (Slow but reliable)
        ]

        last_error = ""

        for model_name in models_to_try:
            try:
                print(f"🔄 Trying model: {model_name}...")
                model = genai.GenerativeModel(model_name)
                response = model.generate_content(prompt)
                
                # Success! Save to cache and return
                result_text = response.text
                explanation_cache[code_hash] = result_text 
                return {"explanation": result_text}

            except Exception as e:
                error_msg = str(e)
                print(f"⚠️ {model_name} failed: {error_msg}")
                last_error = error_msg
                # If it's a 404 (Not Found) or 429 (Busy), we just continue to the next model in the list
                continue

        # If we loop through ALL models and fail:
        if "429" in last_error:
             return {"explanation": "⚠️ All AI models are busy. Please wait 1 minute."}
        
        return {"explanation": f"AI Error: {last_error}"}

    except Exception as e:
        return {"explanation": f"System Error: {str(e)}"}