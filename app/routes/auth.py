from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
import os
import certifi
import bcrypt
from dotenv import load_dotenv
from fastapi import FastAPI, APIRouter, Depends, HTTPException, Form
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, EmailStr, Field
from jose import JWTError, jwt
from pymongo import MongoClient
from bson import ObjectId
# Load env variables
load_dotenv()


SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES"))


MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("DB_NAME")

client = MongoClient(MONGO_URI, tlsCAFile=certifi.where())
db = client[DB_NAME]
users_collection = db["users"]
projects_collection=db["projects"]

router = APIRouter()


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

# Pydantic models
class UserCreate(BaseModel):
    name: str
    email: EmailStr
    password: str
    profile: dict = {}

class UserLogin(BaseModel):
    email: EmailStr
    password: str

# Create JWT token
def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta if expires_delta else timedelta(minutes=15))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

# Signup route
@router.post("/signup")
def signup(user: UserCreate):
    if users_collection.find_one({"email": user.email}):
        raise HTTPException(status_code=400, detail="Email already registered")
    hashed_pw = bcrypt.hashpw(user.password.encode("utf-8"), bcrypt.gensalt())
    new_user = {
        "name": user.name,
        "email": user.email,
        "password_hash": hashed_pw.decode("utf-8"),
        "profile": user.profile
    }
    result = users_collection.insert_one(new_user)
    return {"message": "User created successfully", "user_id": str(result.inserted_id)}

# Login route
@router.post("/login")
def login(user: UserLogin):
    db_user = users_collection.find_one({"email": user.email})
    if not db_user or not bcrypt.checkpw(user.password.encode("utf-8"), db_user["password_hash"].encode("utf-8")):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    access_token = create_access_token({"sub": str(db_user["_id"])}, timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    return {"message": "User logged in successfully", "access_token": access_token, "token_type": "bearer"}

# Get current logged-in user
def get_current_user(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    user = users_collection.find_one({"_id": ObjectId(user_id)})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

# Example protected route
@router.get("/dashboard")
def dashboard(current_user: dict = Depends(get_current_user)):
    return {
        "message": f"Welcome {current_user['name']}!",
        "email": current_user["email"],
        "id": str(current_user["_id"])  # Convert ObjectId to string
    }


class ProjectCreate(BaseModel):
    title: str = Field(..., description="Title of the project")
    description: str = Field(..., description="Detailed description of the project")


@router.post("/create")
async def create_project(
    title: str = Form(...),
    description: str = Form(...),
    current_user: dict = Depends(get_current_user)
):
    # Save project with status "pending"
    new_project = {
        "user_id": str(current_user["_id"]),
        "title": title,
        "description": description,
        "status": "pending",
        "created_at": datetime.utcnow()
    }

    result = projects_collection.insert_one(new_project)
    project_id = str(result.inserted_id)

    return {
        "message": "Project created",
        "project_id": project_id,
        "user_id": str(current_user["_id"])
    }


@router.get("/my-projects")
def get_projects(current_user: dict = Depends(get_current_user)):
    projects_cursor = projects_collection.find({"user_id": str(current_user["_id"])})
    projects: List[Dict[str, Any]] = []
    for p in projects_cursor:
        p["id"] = str(p["_id"])
        # remove raw _id and user_id if you prefer
        p.pop("_id", None)
        projects.append(p)
    return {"projects": projects}


@router.delete("/delete/{project_id}")
def delete_project(
    project_id: str,
    current_user: dict = Depends(get_current_user)
):
    # Check if project exists and belongs to user
    try:
        proj_obj_id = ObjectId(project_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid project id format")

    project = projects_collection.find_one({
        "_id": proj_obj_id,
        "user_id": str(current_user["_id"])
    })
    if not project:
        raise HTTPException(status_code=404, detail="Project not found or not owned by user")

    # Delete project
    projects_collection.delete_one({"_id": proj_obj_id})
    return {"message": "Project deleted successfully", "project_id": project_id}
