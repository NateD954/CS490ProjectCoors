import os
import jwt
import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv

load_dotenv()

CLERK_SECRET_KEY = os.getenv("CLERK_SECRET_KEY")
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY = os.getenv("NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY")

security = HTTPBearer()

def getCurrentUserId(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    """Verifies Clerk using Secret Key and extracts user ID."""
    if not CLERK_SECRET_KEY:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Incorrect CLERK_SECRET_KEY. Please check the .env file."
        )

    token = credentials.credentials
    
    try:
        #Decode header, get key ID 
        unverifiedHeader = jwt.get_unverified_header(token)
        kid = unverifiedHeader.get("kid")

        #Get JWKS from Clerk's API using secret key
        headers = {"Authorization": f"Bearer {CLERK_SECRET_KEY}"}
        
        with httpx.Client() as client:
            res = client.get("https://api.clerk.com/v1/jwks", headers=headers)
            res.raise_for_status()
            jwks = res.json()

        # find matching public key for token
        rsaKey = None
        keys = jwks.get("keys", [])
        
        for key in keys:
            if key.get("kid") == kid:
                rsaKey = key
                break
        
        if not rsaKey:
            raise ValueError("No matching public key found for token.")

        # Verify token using public key
        publicKey = jwt.algorithms.RSAAlgorithm.from_jwk(rsaKey)
        
        payload = jwt.decode(
            token, 
            publicKey, 
            algorithms=["RS256"], 
            options={"verify_exp": True}
        )
        
        return payload["sub"]

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="You do not have permission to access this resource. Please check your credentials."
        )