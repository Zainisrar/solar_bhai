from fastapi import FastAPI
from app.routes import api

app = FastAPI()

# Include routes
app.include_router(api.router)

@app.get("/")
def root():
    return {"message": "Welcome to my FastAPI app"}
