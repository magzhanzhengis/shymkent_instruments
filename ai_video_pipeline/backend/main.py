from fastapi import FastAPI, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import os, time, requests, cloudinary, cloudinary.uploader
import openai

# ------------------- SETUP -------------------
load_dotenv()

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------- API KEYS -------------------
CLOUD_NAME = os.getenv("CLOUD_NAME")
API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")

TWELVELABS_API_KEY = os.getenv("TWELVELABS_API_KEY")
TWELVELABS_INDEX_ID = os.getenv("TWELVELABS_INDEX_ID")
TWELVELABS_API_URL = "https://api.twelvelabs.io/v1.3"

HIGGSFIELD_API_KEY = os.getenv("HIGGSFIELD_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

openai.api_key = OPENAI_API_KEY

# Cloudinary setup
cloudinary.config(cloud_name=CLOUD_NAME, api_key=API_KEY, api_secret=API_SECRET)


# ------------------- HELPERS -------------------

def create_index_if_needed():
    """Auto-create a TwelveLabs index if none exists."""
    if not TWELVELABS_API_KEY:
        return "twelvelabs_not_configured"

    if TWELVELABS_INDEX_ID == "auto" or not TWELVELABS_INDEX_ID:
        try:
            headers = {"x-api-key": TWELVELABS_API_KEY, "Content-Type": "application/json"}
            payload = {
                "index_name": "hackathon_index",
                "models": [{"model_name": "pegasus1.2", "model_options": ["visual", "audio"]}]
            }
            res = requests.post(f"{TWELVELABS_API_URL}/indexes", headers=headers, json=payload)
            print(f"TwelveLabs index creation: {res.status_code} | {res.text}")
            result = res.json()
            return result.get("id", "index_creation_failed")
        except Exception as e:
            return f"error_creating_index: {e}"

    return TWELVELABS_INDEX_ID


def upload_to_cloudinary(video: UploadFile, image: UploadFile):
    """Upload both video and image to Cloudinary and return URLs."""
    video_upload = cloudinary.uploader.upload(video.file, resource_type="video")
    image_upload = cloudinary.uploader.upload(image.file, resource_type="image")
    return video_upload["secure_url"], image_upload["secure_url"]

def analyze_with_twelvelabs(video_url: str, index_id: str):
    """Send video to TwelveLabs and get its description."""
    if not TWELVELABS_API_KEY or "error" in index_id:
        return {"error": f"TwelveLabs not configured or index error: {index_id}"}

    headers = {"x-api-key": TWELVELABS_API_KEY}
    # Don't set Content-Type - requests will set it automatically when using files parameter

    try:
        # Step 1: Upload video to index using multipart/form-data (required by TwelveLabs)
        files = {
            "index_id": (None, index_id),
            "video_url": (None, video_url)
        }
        task_resp = requests.post(f"{TWELVELABS_API_URL}/tasks", headers=headers, files=files)
        print(f"TwelveLabs task response: {task_resp.status_code}")
        print(f"Task response body: {task_resp.text}")
        
        task_result = task_resp.json()
        
        # Extract task_id - TwelveLabs returns it as "_id", "id", or "task_id"
        task_id = task_result.get("_id") or task_result.get("id") or task_result.get("task_id")
        if not task_id:
            return {"error": f"No task_id returned: {task_result}"}

        print(f"TwelveLabs returned task_id: {task_id}")

        # Step 2: Poll task status until completion
        max_retries = 60  # Increased to 60 retries
        retry_count = 0
        status_data = None
        
        while retry_count < max_retries:
            status_resp = requests.get(f"{TWELVELABS_API_URL}/tasks/{task_id}", headers=headers)
            status_data = status_resp.json()
            current_status = status_data.get("status")
            print(f"Task status check {retry_count + 1}/{max_retries}: {current_status}")
            print(f"Full status response: {status_data}")
            
            if current_status == "ready":
                print("Task is ready!")
                break
            elif current_status == "failed":
                return {"error": f"Task failed: {status_data}"}
            elif current_status in ["queued", "indexing", "pending"]:
                # Still processing, continue polling
                pass
            
            time.sleep(10)  # Wait 10 seconds between checks
            retry_count += 1

        if retry_count >= max_retries:
            return {"error": f"Video processing timeout - task did not complete in time. Last status: {status_data}"}

        # Step 3: Extract video_id from the completed task
        video_id = status_data.get("video_id") or task_id
        if not video_id:
            return {"error": f"No video_id in completed task: {status_data}"}

        print(f"Video ID extracted: {video_id}")

        # Step 4: Get video description - try multiple endpoints
        description = None
        
        # Try the /description endpoint first
        try:
            desc_resp = requests.get(
                f"{TWELVELABS_API_URL}/videos/{video_id}/description",
                headers=headers,
                timeout=30
            )
            print(f"Description endpoint status: {desc_resp.status_code}")
            print(f"Description endpoint response: {desc_resp.text}")
            
            if desc_resp.status_code == 200:
                desc_data = desc_resp.json()
                description = desc_data.get("description") or desc_data.get("summary")
        except Exception as e:
            print(f"Error calling description endpoint: {e}")
        
        # If that didn't work, try the summarize endpoint (newer API)
        if not description:
            try:
                print(f"Trying summarize endpoint for video {video_id}...")
                summarize_resp = requests.post(
                    f"{TWELVELABS_API_URL}/summarize",
                    headers=headers,
                    json={"video_id": video_id, "type": "summary"},
                    timeout=30
                )
                print(f"Summarize endpoint status: {summarize_resp.status_code}")
                print(f"Summarize response: {summarize_resp.text}")
                
                if summarize_resp.status_code == 200:
                    summarize_data = summarize_resp.json()
                    description = summarize_data.get("summary") or summarize_data.get("description")
            except Exception as e:
                print(f"Error calling summarize endpoint: {e}")
        
        # If that didn't work, try getting video details
        if not description:
            try:
                video_resp = requests.get(
                    f"{TWELVELABS_API_URL}/videos/{video_id}",
                    headers=headers,
                    timeout=30
                )
                print(f"Video details endpoint status: {video_resp.status_code}")
                print(f"Video details response: {video_resp.text}")
                
                if video_resp.status_code == 200:
                    video_data = video_resp.json()
                    description = (
                        video_data.get("description") or 
                        video_data.get("summary") or 
                        video_data.get("metadata", {}).get("description")
                    )
            except Exception as e:
                print(f"Error calling video details endpoint: {e}")
        
        # If still no description, check the task response itself
        if not description and status_data:
            description = (
                status_data.get("description") or 
                status_data.get("summary") or
                status_data.get("result", {}).get("description")
            )
        
        if not description:
            print("WARNING: No description found from any endpoint")
            description = "Video processed but description unavailable"

        return {
            "video_id": video_id,
            "description": description,
            "status": "ready"
        }

    except Exception as e:
        print(f"Exception in analyze_with_twelvelabs: {str(e)}")
        return {"error": f"TwelveLabs API error: {str(e)}"}
def generate_prompt_with_gpt(video_description: str, user_text: str):
    """Generate creative text prompt for Higgsfield using GPT."""
    if not OPENAI_API_KEY:
        return "OpenAI API key not configured."

    prompt_text = f"""
You are a creative AI prompt engineer. Using the following video description and user idea,
generate a short, cinematic and vivid text prompt for AI video generation.

User idea: {user_text}

Video description:
{video_description}

Write a single detailed prompt that describes what should visually appear in the AI-generated video.
Focus on visuals, motion, color, and emotion. Keep it concise, vivid, and imaginative.
"""

    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": prompt_text}],
        "max_tokens": 250
    }

    try:
        response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=data)
        result = response.json()
        return result["choices"][0]["message"]["content"]
    except Exception as e:
        return f"Error calling GPT API: {e}"


def generate_with_higgsfield(prompt: str, image_url: str):
    """Generate video using Higgsfield with correct headers and payload."""
    
    HIGGSFIELD_API_SECRET = os.getenv("HIGGSFIELD_API_SECRET")
    
    if not HIGGSFIELD_API_KEY or not HIGGSFIELD_API_SECRET:
        return {"error": "HIGGSFIELD_API_KEY or HIGGSFIELD_API_SECRET not configured"}

    try:
        print(f"Submitting to Higgsfield: {prompt[:100]}...")
        
        # CORRECT HEADERS - must use hf-api-key and hf-secret
        headers = {
            "hf-api-key": HIGGSFIELD_API_KEY,
            "hf-secret": HIGGSFIELD_API_SECRET,
            "Content-Type": "application/json"
        }
        
        print(f"API Key set: {bool(HIGGSFIELD_API_KEY)}")
        print(f"API Secret set: {bool(HIGGSFIELD_API_SECRET)}")
        print(f"Headers being sent: {headers}")
        
        # CORRECT PAYLOAD STRUCTURE - params wrapper required
        data = {
            "params": {
                "prompt": prompt,
                "duration": 6,
                "resolution": "768",
                "enable_prompt_optimizer": True
            }
        }
        
        if image_url:
            data["params"]["image_url"] = image_url
        
        print(f"Payload: {data}")
        
        endpoint = "https://platform.higgsfield.ai/generate/minimax-t2v"
        print(f"Endpoint: {endpoint}")
        
        resp = requests.post(endpoint, headers=headers, json=data, timeout=60)
        
        print(f"Response status: {resp.status_code}")
        print(f"Response: {resp.text[:1000]}")
        
        if resp.status_code not in [200, 201]:
            return {"error": f"Higgsfield API error: {resp.status_code} - {resp.text}"}
        
        try:
            result = resp.json()
        except:
            return {"error": f"Invalid response format: {resp.text[:200]}"}
        
        if "error" in result or "detail" in result:
            return {"error": f"Higgsfield error: {result}"}
        
        # Get request ID from response
        request_id = result.get("id") or result.get("request_id") or result.get("uuid")
        if not request_id:
            print(f"No ID in response: {result}")
            return {"error": f"No request ID in response: {result}"}
        
        print(f"Generation started with ID: {request_id}")
        
        # Poll for completion
        max_polls = 120
        poll_interval = 5
        
        for poll_count in range(max_polls):
            try:
                status_endpoint = f"https://platform.higgsfield.ai/generate/minimax-t2v/{request_id}"
                status_resp = requests.get(status_endpoint, headers=headers, timeout=30)
                
                print(f"Poll {poll_count + 1}: {status_resp.status_code}")
                
                if status_resp.status_code == 200:
                    status_data = status_resp.json()
                    status = status_data.get("status")
                    
                    print(f"Status: {status}")
                    
                    if status in ["completed", "success"]:
                        video_url = (
                            status_data.get("video_url") or 
                            status_data.get("url") or 
                            status_data.get("result", {}).get("video_url") or
                            status_data.get("data", {}).get("video_url")
                        )
                        
                        if video_url:
                            print(f"Video ready: {video_url}")
                            return {"video_url": video_url, "status": "success"}
                        else:
                            print(f"Completed but no URL: {status_data}")
                            return {"error": f"No video URL in response: {status_data}"}
                    
                    elif status in ["failed", "error"]:
                        return {"error": f"Generation failed: {status_data.get('error')}"}
                    
                    elif status in ["pending", "processing", "queued"]:
                        time.sleep(poll_interval)
                        continue
                    else:
                        time.sleep(poll_interval)
                        continue
                
                elif status_resp.status_code == 404:
                    time.sleep(poll_interval)
                    continue
                else:
                    print(f"Poll error: {status_resp.status_code}")
                    time.sleep(poll_interval)
                    continue
                    
            except Exception as e:
                print(f"Poll exception: {e}")
                time.sleep(poll_interval)
                continue
        
        return {"error": "Generation timeout"}
    
    except Exception as e:
        print(f"Exception: {str(e)}")
        return {"error": f"Higgsfield API error: {str(e)}"}
@app.post("/process_ai/")
async def process_ai(video: UploadFile, image: UploadFile, text: str = Form(...)):
    """Main pipeline: upload -> describe -> generate prompt -> video."""
    try:
        # 1️⃣ Upload video and image
        video_url, image_url = upload_to_cloudinary(video, image)
        print(f"Uploaded video: {video_url}")
        print(f"Uploaded image: {image_url}")

        # 2️⃣ Create TwelveLabs index
        index_id = create_index_if_needed()
        print(f"Using index_id: {index_id}")

        # 3️⃣ Analyze via TwelveLabs (get description)
        analysis = analyze_with_twelvelabs(video_url, index_id)
        if "error" in analysis:
            return {
                "status": "error",
                "message": f"Video analysis failed: {analysis['error']}",
                "original_video": video_url,
                "image_used": image_url
            }

        description = analysis.get("description", "No description available")
        print(f"Video description: {description}")

        # 4️⃣ Generate GPT prompt
        gpt_prompt = generate_prompt_with_gpt(description, text)
        print(f"Generated prompt: {gpt_prompt[:100]}...")

        # 5️⃣ Generate with Higgsfield
        print("Starting Higgsfield video generation...")
        gen_result = generate_with_higgsfield(gpt_prompt, image_url)
        
        if "error" in gen_result:
            return {
                "status": "partial_success",
                "message": f"Video generation failed: {gen_result['error']}",
                "original_video": video_url,
                "image_used": image_url,
                "description": description,
                "final_prompt": gpt_prompt,
                "generated_video": None
            }

        # 6️⃣ Success
        return {
            "status": "success",
            "original_video": video_url,
            "image_used": image_url,
            "description": description,
            "final_prompt": gpt_prompt,
            "generated_video": gen_result.get("video_url")
        }

    except Exception as e:
        print(f"Pipeline error: {str(e)}")
        return {"status": "error", "message": str(e)}