from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, RedirectResponse

from app.routers.deps import ADMIN_ROLE, LAB_MANAGER_ROLE, STUDENT_ROLE, user_from_request


router = APIRouter(tags=["pages"])


def no_cache_file(path: str):
    return FileResponse(
        path,
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@router.get("/login")
def login_page():
    return no_cache_file("web/templates/login.html")


@router.get("/")
def root(request: Request):
    user = user_from_request(request)
    if not user:
        return RedirectResponse("/login")
    if user.get("role") == STUDENT_ROLE:
        return no_cache_file("web/templates/student_dashboard.html")
    if user.get("role") in {LAB_MANAGER_ROLE, ADMIN_ROLE}:
        return no_cache_file("web/templates/dashboard.html")
    return RedirectResponse("/login")


@router.get("/admin/users")
def users_page(request: Request):
    user = user_from_request(request)
    if not user:
        return RedirectResponse("/login")
    if user.get("role") not in {ADMIN_ROLE, LAB_MANAGER_ROLE}:
        return RedirectResponse("/")
    return RedirectResponse("/?page=accounts")
