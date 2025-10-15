from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
import os

reusable_oauth2 = OAuth2PasswordBearer(tokenUrl="/token", auto_error=False)

SERVER_AUTH_TOKEN = os.getenv("MCP_API_AUTH_TOKEN")

def get_current_user(token: str = Depends(reusable_oauth2)):
    if not SERVER_AUTH_TOKEN:
        # This is a server configuration error, not a client error.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication token not configured on server.",
        )
    
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if token != SERVER_AUTH_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )