from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List
from pymongo import MongoClient
from bson import ObjectId
from dotenv import load_dotenv
import os
from datetime import datetime
import certifi
from openai import OpenAI

# Load env variables
load_dotenv()

router = APIRouter()

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("DB_NAME")

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
# MongoDB collection for NLP
clients = MongoClient(MONGO_URI, tlsCAFile=certifi.where())
db = clients[DB_NAME]
users_collection = db["users"]
nlp_collection = db["nlp"]
# ------------------------------
# Request Model
# ------------------------------
class PromptRequest(BaseModel):
    prompt: str

# Pydantic model for NLP entry
class NLPEntry(BaseModel):
    user_id: str
    prompt: str
    answers: List[str]  # list of answers

# ------------------------------
# LLM Handler Function
# ------------------------------
def send_to_llm(prompt: str) -> List[str]:
    """Send user input to LLM and get 4–5 optimized clarification questions for solar system design."""

    system_prompt = f"""
You are an expert solar system assistant.

A user has described their solar system requirement in natural language. Your job is to:
- Analyze the prompt
- Identify missing or unclear information required to perform load analysis and system sizing (PV, Inverter, Battery)
- Return only **4 to 5 smart, merged questions** that efficiently gather all essential technical details

Each question should combine related data points where possible, to minimize user effort while maximizing information collected.

User Prompt:
\"\"\"
{prompt}
\"\"\"

Output:
A numbered list of 4–5 optimized questions to collect required details for solar system sizing.
"""

    # Example with OpenAI
    response = client.chat.completions.create(
        model="gpt-4.1",
        messages=[
            {"role": "user", "content": system_prompt}
        ]
    )
    raw_text = response.choices[0].message.content.strip()

    questions = []
    for line in raw_text.splitlines():
        if line.strip():
            # Match lines like "1. Question..."
            parts = line.strip().split(".", 1)
            if len(parts) == 2 and parts[0].isdigit():
                questions.append(parts[1].strip())

    return questions


# ------------------------------
# API Route
# ------------------------------
@router.post("/solar/clarify", response_model=List[str])
async def clarify_prompt(data: PromptRequest) -> List[str]:
    try:
        return send_to_llm(data.prompt)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/question_ans_save")
def save_nlp(entry: NLPEntry):
    # Validate user_id
    if not ObjectId.is_valid(entry.user_id):
        raise HTTPException(status_code=400, detail="Invalid user ID format")

    # Check if user exists
    user = users_collection.find_one({"_id": ObjectId(entry.user_id)})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Prepare document
    nlp_doc = {
        "user_id": ObjectId(entry.user_id),
        "prompt": entry.prompt,
        "answers": entry.answers,  # list of answers
        "created_at": datetime.utcnow()
    }

    # Insert into MongoDB
    result = nlp_collection.insert_one(nlp_doc)

    return {
        "message": "NLP entry saved successfully",
        "nlp_id": str(result.inserted_id)
    }

