"""Bridge private workspace identities to Keysi project permissions without exposing keys

Short codes identify a project, while the services backend owns approval and
revision checks. Browser drafts stay mounted when a sign-in window is opened
"""

import os
import re
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

router = APIRouter()


async def _project(request: Request, code: str = "", action: str = "") -> JSONResponse:
    user = request.app.state.identity.owner(request)
    if not user:
        raise HTTPException(
            401, "Reload Minis to reconnect your workspace; your draft is still here"
        )
    if code and not re.fullmatch(r"[A-Za-z0-9_-]{12}", code):
        raise HTTPException(400, "Use the twelve-character code from the owner’s link")
    origin = os.environ.get("KEYSI_SERVICES_URL", "http://127.0.0.1:8788").rstrip("/")
    parsed = urlsplit(origin)
    if parsed.scheme != "https" and not (
        parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost"}
    ):
        raise HTTPException(503, "The sharing service needs a secure connection")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise HTTPException(503, "The sharing service address needs correcting")
    key = os.environ.get("KEYSI_MINIS_KEY", "")
    if not key and parsed.hostname in {"127.0.0.1", "localhost"}:
        path = Path(__file__).resolve().parents[4] / "services/.keysi/minis.key"
        if path.is_file() and not path.is_symlink():
            key = path.read_text().strip()
    if not key:
        raise HTTPException(503, "Start the Keysi sharing service to connect this draft")
    path = "/api/projects" + (f"/{code}" if code else "") + (f"/{action}" if action else "")
    body = await request.body()
    if len(body) > 128 * 1024:
        raise HTTPException(413, "Keep the shared project notes under 128 KiB")
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
            response = await client.request(
                request.method,
                origin + path,
                headers={
                    "Authorization": f"Bearer {key}",
                    "X-Keysi-User": user,
                    "Content-Type": "application/json",
                },
                content=body,
            )
    except httpx.RequestError as error:
        raise HTTPException(
            503, "The sharing desk couldn't be reached; your local draft is safe"
        ) from error
    try:
        data = response.json()
    except ValueError as error:
        raise HTTPException(
            502, "The sharing service returned an unreadable reply; try again"
        ) from error
    return JSONResponse(data, status_code=response.status_code)


@router.api_route("/api/timey/projects", methods=["GET", "POST"])
async def projects(request: Request) -> JSONResponse:
    """List or create projects owned by this private workspace"""
    return await _project(request)


@router.api_route("/api/timey/projects/{code}", methods=["GET", "PUT"])
async def project(request: Request, code: str) -> JSONResponse:
    """Read or save only an approved project revision"""
    return await _project(request, code)


@router.post("/api/timey/projects/{code}/request")
async def join(request: Request, code: str) -> JSONResponse:
    """Ask the owner for access without returning the project’s private contents"""
    return await _project(request, code, "request")


@router.put("/api/timey/projects/{code}/access")
async def access(request: Request, code: str) -> JSONResponse:
    """Let the owner approve or reject a request"""
    return await _project(request, code, "access")
