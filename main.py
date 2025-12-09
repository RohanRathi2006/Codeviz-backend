from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from services.file_service import clone_repository, delete_repository
from services.parser_service import parse_repo
from fastapi.middleware.cors import CORSMiddleware
import traceback
import os
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
    Uses the 'Lite' model to avoid Rate Limits (429 errors).
    """
    if not GOOGLE_API_KEY:
        return {"explanation": "⚠️ Server Error: API Key not configured. Check .env file."}

    try:
        genai.configure(api_key=GOOGLE_API_KEY)
        code_snippet = request.code[:2000] 
        prompt = f"You are a Senior Software Architect. Explain this code file briefly in 3 clear bullet points. Focus on its role in the system architecture:\n\n{code_snippet}"

        # FIX: Use 'gemini-2.0-flash-lite' (Found in your list)
        # This model is optimized for speed and has better rate limits.
        model = genai.GenerativeModel("gemini-2.0-flash-lite")
        
        response = model.generate_content(prompt)
        return {"explanation": response.text}

    except Exception as e:
        error_msg = str(e)
        print(f"AI Error: {error_msg}")
        
        # If Lite fails, try the generic 'flash-latest' alias as a backup
        if "404" in error_msg:
             try:
                 print("⚠️ Lite model not found, trying 'gemini-flash-latest'...")
                 model = genai.GenerativeModel("gemini-flash-latest")
                 response = model.generate_content(prompt)
                 return {"explanation": response.text}
             except Exception as inner_e:
                 return {"explanation": f"AI Error: {str(inner_e)}"}

        if "429" in error_msg:
            return {"explanation": "⚠️ AI usage limit reached. Please wait 30 seconds."}
            
        return {"explanation": f"AI Error: {error_msg}"}