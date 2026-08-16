"""
Connection Test Script
Tests all external connections in the AI Project OS
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load environment
load_dotenv()

print("=" * 60)
print("AI PROJECT OS - CONNECTION TEST")
print("=" * 60)

# Test 1: Database Connection
print("\n[1] DATABASE CONNECTION")
print("-" * 60)
try:
    from sqlalchemy import text
    from backend.database import engine
    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1"))
        print("✓ Database connection: SUCCESS")
        print(f"  Database URL: {os.getenv('DATABASE_URL', 'NOT SET')[:60]}...")
except Exception as e:
    print(f"✗ Database connection: FAILED")
    print(f"  Error: {str(e)}")

# Test 2: API Base URL
print("\n[2] API BASE URL")
print("-" * 60)
api_url = os.getenv("API_BASE_URL", "http://localhost:8000")
print(f"  API_BASE_URL: {api_url}")
try:
    import requests
    response = requests.get(f"{api_url}/docs", timeout=3)
    if response.status_code == 200:
        print("✓ API Server: ACCESSIBLE")
    else:
        print(f"✓ API Server: Responding ({response.status_code})")
except requests.exceptions.ConnectionError:
    print(f"✗ API Server: NOT RUNNING (cannot connect to {api_url})")
except Exception as e:
    print(f"! API Server: {str(e)}")

# Test 3: JWT Configuration
print("\n[3] JWT CONFIGURATION")
print("-" * 60)
jwt_secret = os.getenv("JWT_SECRET")
jwt_algorithm = os.getenv("JWT_ALGORITHM")
if jwt_secret and len(jwt_secret) >= 8:
    print(f"✓ JWT_SECRET: Set (length: {len(jwt_secret)})")
else:
    print(f"✗ JWT_SECRET: Missing or too short")
if jwt_algorithm:
    print(f"✓ JWT_ALGORITHM: {jwt_algorithm}")
else:
    print(f"✗ JWT_ALGORITHM: Not set")

# Test 4: LLM API Keys
print("\n[4] LLM API KEYS")
print("-" * 60)

gemini_key = os.getenv("GEMINI_API_KEY")
if gemini_key:
    print(f"✓ GEMINI_API_KEY: Set")
    try:
        import google.generativeai as genai
        genai.configure(api_key=gemini_key)
        model = genai.GenerativeModel(os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite"))
        print(f"✓ GEMINI Model: {os.getenv('GEMINI_MODEL')} (configured)")
    except Exception as e:
        print(f"✗ GEMINI Configuration: {str(e)}")
else:
    print(f"✗ GEMINI_API_KEY: NOT SET")

groq_key = os.getenv("GROQ_API_KEY")
if groq_key:
    print(f"✓ GROQ_API_KEY: Set")
    try:
        from groq import Groq
        client = Groq(api_key=groq_key)
        print(f"✓ GROQ Client: Ready")
    except Exception as e:
        print(f"✗ GROQ Configuration: {str(e)}")
else:
    print(f"✗ GROQ_API_KEY: NOT SET")

openai_key = os.getenv("OPENAI_API_KEY")
if openai_key:
    print(f"✓ OPENAI_API_KEY: Set")
else:
    print(f"! OPENAI_API_KEY: Not configured (optional)")

# Test 5: Python Packages
print("\n[5] REQUIRED PACKAGES")
print("-" * 60)
packages_to_check = [
    "fastapi", "uvicorn", "sqlalchemy", "pydantic", 
    "python_jose", "psycopg2", "python_dotenv",
    "requests", "streamlit"
]

for package in packages_to_check:
    try:
        __import__(package.replace("-", "_"))
        print(f"✓ {package}")
    except ImportError:
        print(f"✗ {package}: NOT INSTALLED")

# Test 6: RAG Dependencies (Optional)
print("\n[6] RAG DEPENDENCIES (Optional)")
print("-" * 60)
rag_packages = ["sentence_transformers", "pypdf", "python_docx"]
for package in rag_packages:
    try:
        __import__(package.replace("-", "_"))
        print(f"✓ {package}")
    except ImportError:
        print(f"! {package}: Not installed (optional for RAG features)")

# Test 7: Environment Variables Summary
print("\n[7] ENVIRONMENT VARIABLES SUMMARY")
print("-" * 60)
required_env_vars = {
    "DATABASE_URL": "PostgreSQL/SQLite connection string",
    "JWT_SECRET": "Secret key for JWT tokens",
    "JWT_ALGORITHM": "Algorithm for JWT (usually HS256)",
    "API_BASE_URL": "Backend API URL (defaults to http://localhost:8000)",
}

missing = []
for var, description in required_env_vars.items():
    value = os.getenv(var)
    if value:
        masked = value if len(value) < 20 else value[:20] + "..."
        print(f"✓ {var}: {masked}")
    else:
        print(f"✗ {var}: NOT SET")
        missing.append(var)

if missing:
    print(f"\n⚠ Missing required variables: {', '.join(missing)}")
    print("  Update your .env file or set environment variables.")
else:
    print("\n✓ All required variables are set!")

print("\n" + "=" * 60)
print("CONNECTION TEST COMPLETE")
print("=" * 60)
