from fastapi.middleware.cors import CORSMiddleware
from app.db import supabaseClient
from fastapi import FastAPI, Depends, HTTPException, status
from pydantic import BaseModel
from app.auth import getCurrentUserId

app = FastAPI(title="ReviewLens Coors edition (/^-^)o日日o(|^0^|) Backend Fastest API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class TargetCreateRequest(BaseModel):
    name: str
    platform: str
    sourceUrl: str

def verifyTargetOwnership(targetId: str, authenticatedUserId: str) -> dict:
    res = supabaseClient.table("analysis_targets").select("*").eq("id", targetId).execute()
    if not res.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target not found. Please check the target ID and try again.")

    target = res.data[0]
    if target.get("user_id") != authenticatedUserId:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access forbidden: Analysis target access violation. Please check the target ID and user ID and try again."
        )
    return target

@app.post("/api/targets", status_code=status.HTTP_201_CREATED)
def createTarget(body: TargetCreateRequest, userId: str = Depends(getCurrentUserId)):
    targetData = {
        "name": body.name,
        "platform": body.platform,
        "source_url": body.sourceUrl,
        "user_id": userId
    }
    res = supabaseClient.table("analysis_targets").insert(targetData).execute()
    return res.data[0]

@app.get("/api/targets/{targetId}")
def getTarget(targetId: str, userId: str = Depends(getCurrentUserId)):
    return verifyTargetOwnership(targetId, userId)

@app.get("/api/targets/{targetId}/reviews")
def getTargetReviews(targetId: str, userId: str = Depends(getCurrentUserId)):
    verifyTargetOwnership(targetId, userId)
    reviewsRes = supabaseClient.table("reviews").select("*").eq("target_id", targetId).execute()
    return reviewsRes.data