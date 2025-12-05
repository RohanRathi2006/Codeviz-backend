import google.generativeai as genai

# Paste your key here just for this test
genai.configure(api_key="AIzaSyCponxtZA9atROZU5ejs5tZdRD5SXJUJAI")

print("Listing available models...")
for m in genai.list_models():
    if 'generateContent' in m.supported_generation_methods:
        print(f"- {m.name}")