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
import base64
import cloudinary
import cloudinary.uploader

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
projects_collection=db["projects"]

def from_gemini(user_prompt: str, api_key: str):
    try:
        genai.configure(api_key=api_key)
    except Exception as e:
        return json.dumps({"error": f"Failed to configure Gemini API: {e}"}, indent=2)

    # Updated meta-prompt for short one-line recommendation
    meta_prompt = """
    You are an expert in solar PV & battery system sizing.
    Based on the user's provided load details, location, or requirements,
    give ONLY a single short recommendation in this exact format:
    "<PV size in kW> <On-Grid or Off-Grid> PV & <Battery capacity in kWh> Battery System."
    Do not explain, do not add extra text, output only that one sentence.
    """

    full_prompt = meta_prompt + "\n\nUser Request: \"" + user_prompt + "\""

    try:
        model = genai.GenerativeModel('gemini-2.5-pro')
        response = model.generate_content(full_prompt)

        return response
    except Exception as e:
        return json.dumps({"error": f"Failed to generate content: {e}"}, indent=2)
class LoadAnalysisRequest(BaseModel):
    user_id: str
    nlp_id: str
    project_id: str
@router.post("/sdl")
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
        output = from_gemini(combined_text, my_api_key)
        prompt_image=f"""generate image of Technical engineering schematic, black-and-white, showing a clean and professional electrical diagram of a “{output}” Include: solar PV arrays with multiple rectangular panel icons connected in parallel, DC combiner box, SPD (surge protection device), hybrid inverter symbol, lithium battery bank, AC and DC breakers, optional generator symbol, and grid connection. Show all wiring with straight clean lines and arrow direction, labeled with wire size, amperage, and voltage. Add a “Nomenclature” box listing components (Solar PV Array, DC Combiner Box, DCDB, SPD). Include an “Equipment Details” table with solar PV module specs, battery module specs, and inverter capacity. Add a “PV String Configuration Details” table showing total PV array capacity, module capacity, and total array wattage. Use standard electrical symbols, clear text labels, proportionate spacing, and minimalistic professional blueprint style."""
        result = client.images.generate(
            model="gpt-image-1",
            prompt=prompt_image
        )

        image_base64 = result.data[0].b64_json
        image_bytes = base64.b64decode(image_base64)
        image_path = "otter.png"
        # Save the image to a file
        with open(image_path, "wb") as f:
            f.write(image_bytes)

        # Configure Cloudinary
        cloudinary.config(
            cloud_name="dtkxm4abz",
            api_key=os.getenv("CLOUD_API_KEY"),
            api_secret=os.getenv("CLOUD_API_SECRET")
        )

        # Upload the image
        upload_result = cloudinary.uploader.upload(image_path)

        # Get the secure URL
        image_url = upload_result["secure_url"]
        projects_collection.update_one(
            {"_id": ObjectId(project_id)},
            {"$set": {"image_url": image_url}}
        )

        return image_url
    except Exception as e:
        return {"error": str(e)}


@router.get("/project-image/{project_id}")
def get_project_image_url(project_id: str):
    try:
        project = projects_collection.find_one({"_id": ObjectId(project_id)}, {"image_url": 1, "_id": 0})
        if not project or "image_url" not in project:
            raise HTTPException(status_code=404, detail="Image URL not found for this project")
        response = client.responses.create(
        model="gpt-4.1-mini",
        input=[{
        "role": "user",
        "content": [
            {
                "type": "input_text",
                "text": """You are given an electrical schematic diagram of a 20 kW On-Grid PV & Battery System.
Generate a detailed Bill of Materials (BOM) containing only the component list with realistic quantities and specifications.
Do NOT include prices.

The BOM should include all major components such as:
- Solar PV modules (with realistic wattage, type, and quantity)
- Mounting structures
- DC combiner box
- DC and AC breakers
- Surge protection devices (SPD)
- Hybrid inverter
- Battery bank (chemistry, voltage, capacity in Ah and kWh)
- Cables (type, size, and approximate total lengths)
- Connectors, fuses, monitoring devices, grounding kits, accessories, and safety equipment

Ensure the specifications are realistic for a 20 kW on-grid PV system with lithium battery storage.

Return the result strictly in JSON format with this structure:

{
  "BOM": [
    {
      "item": "Solar PV Module",
      "specs": "400 W Polycrystalline, 72-cell",
      "quantity": 50,
      "unit": "pcs"
    },
    {
      "item": "Hybrid Inverter",
      "specs": "20 kW, 3-phase, MPPT input 200-450V DC",
      "quantity": 1,
      "unit": "unit"
    },
    {
      "item": "Battery Bank",
      "specs": "Lithium Iron Phosphate (LiFePO4), 51.2 V, 600 Ah (~30.7 kWh)",
      "quantity": 1,
      "unit": "bank"
    }
    // Continue listing all relevant components
  ]
}
"""
            },
            {
                "type": "input_image",
                "image_url": project["image_url"],
            },
        ],
    }],
)


        
        cleaned_response = response.output_text.strip().replace("```json", "").replace("```", "")
        
        # Validate and format the JSON
        parsed_json = json.loads(cleaned_response)
        return parsed_json
    except Exception as e:
        return {"error": str(e)}


class LoadAnalysisRequest(BaseModel):
    user_id: str
    nlp_id: str
    project_id: str


def from_LLM(user_prompt: str, api_key: str):
    try:
        genai.configure(api_key=api_key)
    except Exception as e:
        return json.dumps({"error": f"Failed to configure Gemini API: {e}"}, indent=2)

    # Updated meta-prompt for short one-line recommendation
    meta_prompt = """
    Based on user text ,convert into like this image prompt:
    example image prompt:
    Create a professional 2D rooftop solar electrical plan in architectural drawing style. Show the house roof layout from top view, with labeled roof sections, property line, driveway, street name, and north arrow. Indicate solar panel module placement with numbered symbols inside a shaded installation area. Include fire pathways, conduit runs, electrical components such as MSP (main service panel), ACD (AC disconnect), CB (combiner box), and UM (utility meter) with labels. Add a legend box explaining symbols, a title block on the right with customer address, project name, scale, date, and system size details. Use clean CAD-like lines, minimal colors, and professional drafting conventions.
    only generate image prompt.Now, analyze the following user request:
    """

    full_prompt = meta_prompt + "\n\nUser Text: \"" + user_prompt + "\""



    try:
        model = genai.GenerativeModel('gemini-2.5-pro')
        response = model.generate_content(full_prompt)

        # Clean up the response to ensure it's valid JSON
        # Models can sometimes include markdown formatting like ```json
        cleaned_response = response.text.strip()

        return cleaned_response
    except Exception as e:
        return json.dumps({"error": f"Failed to generate content: {e}"}, indent=2)

        
@router.post("/CAD")
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
        output = from_LLM(combined_text, my_api_key)
        result = client.images.generate(
            model="gpt-image-1",
            prompt=output
        )

        image_base64 = result.data[0].b64_json
        image_bytes = base64.b64decode(image_base64)
        image_path = "otr.png"
        # Save the image to a file
        with open(image_path, "wb") as f:
            f.write(image_bytes)

        # Configure Cloudinary
        cloudinary.config(
            cloud_name="dtkxm4abz",
            api_key=os.getenv("CLOUD_API_KEY"),
            api_secret=os.getenv("CLOUD_API_SECRET")
        )

        # Upload the image
        upload_result = cloudinary.uploader.upload(image_path)

        # Get the secure URL
        image_url = upload_result["secure_url"]
        projects_collection.update_one(
            {"_id": ObjectId(project_id)},
            {"$set": {"image_url": image_url}}
        )

        return image_url
    except Exception as e:
        return {"error": str(e)}