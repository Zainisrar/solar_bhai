from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routes import auth , question # your signup/login API file

app = FastAPI()

# CORS settings
origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include your API routes
app.include_router(auth.router)
app.include_router(question.router)

# Root route
@app.get("/")
def root():
    return {"message": "Welcome to My Pinterest Downloader & FastAPI App"}
