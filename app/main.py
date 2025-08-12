from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routes import auth , question , Load_analysis, sdl, weather # your signup/login API file

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
app.include_router(Load_analysis.router)
app.include_router(sdl.router)
app.include_router(weather.router)


# Root route
@app.get("/")
def root():
    return {"message": "Welcome to My Pinterest Downloader & FastAPI App"}
