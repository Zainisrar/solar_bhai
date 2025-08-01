from fastapi import APIRouter, File, Depends, HTTPException
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, EmailStr
from pymongo import MongoClient
from bson import ObjectId
from dotenv import load_dotenv
import os
import bcrypt

from fastapi.security import OAuth2PasswordBearer
from bson import ObjectId
from dotenv import load_dotenv
import os
import bcrypt
from datetime import datetime, timedelta
from jose import JWTError, jwt
from fastapi.security import OAuth2PasswordBearer
import certifi
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
    return {"message": f"Welcome {current_user['name']}!", "email": current_user["email"]}
