from fastapi import APIRouter, HTTPException, Body
from pymongo import MongoClient
from dotenv import load_dotenv
import os
from dotenv import load_dotenv
import os
import bcrypt
from openai import OpenAI  # Or your LLM client wrapper
import certifi
import os
import json
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
weather_collection=db["weather"]



router = APIRouter()

def get_json_from_gemini(user_input: str, api_key: str):
    """
    """
    try:
        genai.configure(api_key=api_key)
    except Exception as e:
        return json.dumps({"error": f"Failed to configure Gemini API: {e}"}, indent=2)

    # The "system instruction" or "meta-prompt" that guides the model's behavior.
    # This is crucial for getting reliable, structured JSON output.
    meta_prompt = """
    You are an expert solar energy system designer.

    Task:
    Given the following location and load information, calculate and present a complete solar yield estimation report in JSON format.

    Requirements:
    1. Use realistic solar radiation data for the given location.
    2. Assume a hybrid solar + grid + battery backup system.
    3. Account for system losses, inverter efficiency, and battery round-trip efficiency.
    4. The JSON must follow the structure shown in the example.
    5. All energy values should be in kWh, power values in kW, efficiency as a percentage.
    6. Monthly generation should include all 12 months.

    Example JSON output:
{
  "systemAssumptions": {
    "location": "Rawalpindi/Islamabad region, Pakistan (user-specified)",
    "peakSunHours_monthly_used_for_estimate": {
      "Jan": 4.8,
      "Feb": 5.2,
      "Mar": 5.8,
      "Apr": 6.4,
      "May": 6.9,
      "Jun": 6.6,
      "Jul": 6.2,
      "Aug": 5.9,
      "Sep": 5.8,
      "Oct": 5.6,
      "Nov": 5.0,
      "Dec": 4.7
    },
    "pv_system_derate_percent": 20,
    "inverter_efficiency_percent": 95,
    "battery_round_trip_efficiency_percent": 90,
    "battery_depth_of_discharge_percent": 80,
    "panel_power_standard": "approx. 330-350 W per panel assumed for panel count estimates",
    "notes": "PSH (peak sun hours) values are monthly average estimates for the Islamabad/Rawalpindi area used to generate monthly PV yields. System derate covers soiling, temperature losses, wiring, mismatch, and other balance-of-system losses. Inverter and battery efficiency assumptions are typical modern values."
  },
  "monthlyGeneration_kWh": [
    { "month": "January", "days": 31, "daily_kWh_from_PV": 6.33, "monthly_kWh_from_PV": 196.416 },
    { "month": "February", "days": 28, "daily_kWh_from_PV": 6.864, "monthly_kWh_from_PV": 192.192 },
    { "month": "March", "days": 31, "daily_kWh_from_PV": 7.656, "monthly_kWh_from_PV": 237.336 },
    { "month": "April", "days": 30, "daily_kWh_from_PV": 8.448, "monthly_kWh_from_PV": 253.44 },
    { "month": "May", "days": 31, "daily_kWh_from_PV": 9.108, "monthly_kWh_from_PV": 282.348 },
    { "month": "June", "days": 30, "daily_kWh_from_PV": 8.712, "monthly_kWh_from_PV": 261.36 },
    { "month": "July", "days": 31, "daily_kWh_from_PV": 8.184, "monthly_kWh_from_PV": 253.704 },
    { "month": "August", "days": 31, "daily_kWh_from_PV": 7.788, "monthly_kWh_from_PV": 241.428 },
    { "month": "September", "days": 30, "daily_kWh_from_PV": 7.656, "monthly_kWh_from_PV": 229.68 },
    { "month": "October", "days": 31, "daily_kWh_from_PV": 7.392, "monthly_kWh_from_PV": 229.152 },
    { "month": "November", "days": 30, "daily_kWh_from_PV": 6.6, "monthly_kWh_from_PV": 198.0 },
    { "month": "December", "days": 31, "daily_kWh_from_PV": 6.204, "monthly_kWh_from_PV": 192.324 }
  ],
  "annualSummary": {
    "annual_kWh_from_PV": 2767.38,
    "average_daily_kWh_from_PV": 7.58,
    "daily_consumption_kWh": 3.04,
    "surplus_or_deficit_daily_kWh": 4.54,
    "notes": "The PV system (1.65 kWp) is sized to produce on average ~7.58 kWh/day after system derate — enough to supply the daily consumption (~3.04 kWh) and to recharge the battery for an 8-hour full-load backup when needed. Because the user is grid-connected and wants hybrid operation, the grid can be used to make up shortfalls during prolonged bad-weather periods."
  },
  "implementationNotes": {
    "panel_count_estimate": "4-6 panels recommended; 5 x 330W ≈ 1.65 kWp is a practical option if roof area allows",
    "recommended_actions": [
      "Confirm local shading and roof azimuth/tilt to optimize actual production (this estimate assumes unobstructed southern exposure at typical tilt).",
      "Use a hybrid inverter with battery management and automatic grid transfer.",
      "Specify lithium-ion battery with at least 5 kWh nominal capacity (usable ≈ 4.0 kWh at 80% DoD) to reliably supply the 8-hour full-load backup.",
      "Consider oversizing PV slightly (10–20%) if future load growth is expected or to ensure faster battery recharge on cloudy days."
    ]
  }
}

    """
    full_prompt = meta_prompt + "\n\nUser Request: \"" + user_input + "\""

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


@router.post("/combine-data")
def combine_data(
    user_id: str = Body(...),
    project_id: str = Body(...),
    load_id: str = Body(...)
):
    # Fetch document from MongoDB
    doc = load_collection.find_one(
        {
            "_id": ObjectId(load_id),
            "user_id": ObjectId(user_id),
            "project_id": ObjectId(project_id)
        },
        {"text": 1, "_id": 0}  # Only get the text field
    )

    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    if "text" not in doc:
        raise HTTPException(status_code=400, detail="'text' field missing in document")

    text_data = doc["text"]

    json_output = get_json_from_gemini(text_data, my_api_key)

    try:
        parsed_data = json.loads(json_output)
        if not parsed_data:
            raise HTTPException(status_code=400, detail="No data provided")
        
        result = weather_collection.insert_one(parsed_data)
        return {"inserted_id": str(result.inserted_id)}

    except (json.JSONDecodeError, TypeError) as e:
        raise HTTPException(status_code=500, detail=f"Invalid JSON from Gemini: {e}")


@router.get("/weather/{weather_id}")
def get_weather(weather_id: str):
    doc = weather_collection.find_one({"_id": ObjectId(weather_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    doc["_id"] = str(doc["_id"])
    return doc