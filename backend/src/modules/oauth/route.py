from typing import Annotated

from fastapi import APIRouter, Depends

from .dependency import verify_firebase_token

router = APIRouter()


# Dependency to verify the token for routes in this router


# A protected route inside your APIRouter
@router.get("/profile")
def get_user_profile(
    decoded_token: Annotated[dict, Depends(verify_firebase_token)],
):
    return {
        "message": "Successfully retrieved profile",
        "uid": decoded_token.get("uid"),
        "email": decoded_token.get("email")
    }
