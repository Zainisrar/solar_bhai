from fastapi import APIRouter, File, Depends, HTTPException
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, EmailStr
from pymongo import MongoClient
from bson import ObjectId
from dotenv import load_dotenv
import os
import bcrypt
from typing import List
from fastapi.security import OAuth2PasswordBearer
from bson import ObjectId
from dotenv import load_dotenv
import os
import bcrypt
from datetime import datetime, timedelta
from jose import JWTError, jwt
from fastapi.security import OAuth2PasswordBearer
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Any
from openai import OpenAI  # Or your LLM client wrapper
from fastapi import Body
from pydantic import BaseModel
from datetime import datetime
import certifi
from bson import ObjectId
import os
import json
import google.generativeai as genai
# Load env variables
load_dotenv()

router = APIRouter()

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("DB_NAME")
my_api_key = os.getenv("GEN_API_KEY")
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
# MongoDB collection for NLP
clients = MongoClient(MONGO_URI, tlsCAFile=certifi.where())
db = clients[DB_NAME]
users_collection = db["users"]
nlp_collection = db["nlp"]
load_collection = db["load"]

def get_json_from_gemini(user_prompt: str, api_key: str):
    """
    Calls the Gemini API with a specific prompt to get a load analysis in JSON format.

    Args:
        user_prompt (str): The user's simple request (e.g., "I have 2 fans and a fridge").
        api_key (str): Your Google API Key for Gemini.

    Returns:
        str: A JSON formatted string with the load analysis and system sizing.
    """
    try:
        genai.configure(api_key=api_key)
    except Exception as e:
        return json.dumps({"error": f"Failed to configure Gemini API: {e}"}, indent=2)

    # The "system instruction" or "meta-prompt" that guides the model's behavior.
    # This is crucial for getting reliable, structured JSON output.
    meta_prompt = """
    You are an AI-Powered Solar System Designer. Your task is to perform a load analysis and preliminary system sizing based on a user's description of their appliances.

    Analyze the user's prompt and generate a single, complete JSON object. Do NOT include any text or formatting before or after the JSON object.

    The JSON object must have the following structure:
    {
      "analysisSummary": {
        "totalDailyEnergyConsumption_kWh": "float",
        "peakContinuousLoad_kW": "float",
        "estimatedSurgeLoad_kW": "float",
        "notes": "string with any relevant assumptions made"
      },
      "detailedLoadList": [
        {
          "appliance": "string",
          "quantity": "integer",
          "powerRating_W": "integer",
          "dailyOperatingHours": "integer",
          "dailyEnergy_Wh": "integer",
          "isMotorLoad": "boolean"
        }
      ],
      "preliminarySizingRecommendations": {
        "inverter": {
          "continuousPower_kW": "float",
          "surgePower_kW": "float",
          "notes": "string explaining the sizing, including a 25% safety margin on continuous power."
        },
        "batteryBank": {
          "totalCapacity_kWh": "float",
          "usableCapacity_kWh": "float",
          "notes": "string explaining sizing assumptions, like 2 days of autonomy and 80% Depth of Discharge (DoD)."
        },
        "pvArray": {
          "requiredPower_kWp": "float",
          "notes": "string explaining sizing, assuming 4 Peak Sun Hours (PSH) and accounting for system losses."
        }
      }
    }

    Use typical power ratings and daily usage hours for common appliances. Clearly state your assumptions in the 'notes' fields. The `estimatedSurgeLoad_kW` should account for the largest motor's startup surge plus other running loads.
    
    Now, analyze the following user request:
    """

    # Combine the instruction prompt with the user's actual request
    full_prompt = meta_prompt + "\n\nUser Request: \"" + user_prompt + "\""

    try:
        model = genai.GenerativeModel('gemini-2.5-pro')
        response = model.generate_content(full_prompt)

        # Clean up the response to ensure it's valid JSON
        # Models can sometimes include markdown formatting like ```json
        cleaned_response = response.text.strip().replace("```json", "").replace("```", "")
        
        # Validate and format the JSON
        parsed_json = json.loads(cleaned_response)
        return json.dumps(parsed_json, indent=2)

    except Exception as e:
        return json.dumps({"error": f"An error occurred while calling the API or parsing the response: {e}", "raw_response": response.text if 'response' in locals() else "No response received."}, indent=2)


class LoadAnalysisRequest(BaseModel):
    user_id: str  # from users collection
    nlp_id: str   # _id of the nlp_collection document
    project_id:str

@router.post("/nlp/load_analysis")
def get_user_prompt_and_answers_as_string(request: LoadAnalysisRequest):
    try:
        user_id = request.user_id
        nlp_id = request.nlp_id
        project_id = request.project_id

        # 1️⃣ Get specific NLP document by user_id & _id
        doc = nlp_collection.find_one(
            {
                "_id": ObjectId(nlp_id),
                "user_id": ObjectId(user_id),
                "project_id": ObjectId(project_id)  # ✅ Added check for project_id
            },
            {"prompt": 1, "answers": 1, "_id": 0}
        )


        if not doc:
            raise HTTPException(status_code=404, detail="NLP record not found")

        # 2️⃣ Combine into one string for Gemini
        combined_text = doc["prompt"] + "\n" + "\n".join(doc.get("answers", []))

        # 3️⃣ Call Gemini to get JSON analysis
        json_output = get_json_from_gemini(combined_text, my_api_key)
        json_str = json.dumps(json_output)
        final_str = combined_text + json_str
        # 4️⃣ Parse the Gemini JSON output
        try:
            parsed_data = json.loads(json_output)
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=500, detail=f"Invalid JSON from Gemini: {e}")

        # 5️⃣ Extract required keys
        analysis_summary = parsed_data.get("analysisSummary", {})
        detailed_load_list = parsed_data.get("detailedLoadList", [])
        preliminary_sizing_recommendations = parsed_data.get("preliminarySizingRecommendations", {})

        # 6️⃣ Insert into `load_collection`
        result=load_collection.insert_one({
            "user_id": ObjectId(user_id),
            "nlp_id": ObjectId(nlp_id),
            "project_id":ObjectId(project_id),
            "text":final_str,
            "analysisSummary": analysis_summary,
            "detailedLoadList": detailed_load_list,
            "preliminarySizingRecommendations": preliminary_sizing_recommendations,
            "created_at": datetime.utcnow()
        })


        # 7️⃣ Return confirmation
        return {
            "status": "success",
            "message": "Data stored in load collection successfully",
            "load_id": str(result.inserted_id)
        }

    except Exception as e:
        print("Error:", e)
        raise HTTPException(status_code=500, detail="Failed to fetch, analyze, or store data")


@router.get("/nlp/load_analysis/{user_id}/{load_id}")
def get_load_analysis(user_id: str, load_id: str):
    try:
        # Query with both IDs
        query = {
            "_id": ObjectId(load_id),
            "user_id": ObjectId(user_id)
        }

        doc = load_collection.find_one(query)

        if not doc:
            raise HTTPException(
                status_code=404,
                detail="No load analysis found for this user_id and load_id"
            )

        # Convert ObjectId to string for JSON
        doc["_id"] = str(doc["_id"])
        doc["user_id"] = str(doc["user_id"])
        if "nlp_id" in doc:
            doc["nlp_id"] = str(doc["nlp_id"])

        return {
            "status": "success",
            "data": doc
        }

    except Exception as e:
        print("Error:", e)
        raise HTTPException(
            status_code=500,
            detail="Failed to fetch load analysis data"
        )



