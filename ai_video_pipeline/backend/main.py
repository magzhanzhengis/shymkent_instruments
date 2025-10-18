from fastapi import FastAPI, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import cloudinary
import cloudinary.uploader
import os

# Load environment variables
load_dotenv()

CLOUD_NAME = os.getenv("CLOUD_NAME")
API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")

# Configure Cloudinary
cloudinary.config(
    cloud_name=CLOUD_NAME,
    api_key=API_KEY,
    api_secret=API_SECRET
)

app = FastAPI()

# Allow frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return {"message": "Backend running"}

@app.post("/process/")
async def process(video: UploadFile, image: UploadFile, text: str = Form(...)):
    # Upload video to Cloudinary
    video_result = cloudinary.uploader.upload(video.file, resource_type="video")
    image_result = cloudinary.uploader.upload(image.file, resource_type="image")

    return {
        "status": "uploaded",
        "text": text,
        "video_url": video_result["secure_url"],
        "image_url": image_result["secure_url"]
    }
