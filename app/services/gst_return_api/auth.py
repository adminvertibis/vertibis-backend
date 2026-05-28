from typing import Any

from app.services.gst_return_api.client import GSTReturnAPIClient
from app.services.gst_return_api.models import GSTAPIResult


AUTH_PATH = "/taxpayerapi/dec/v1.0/authenticate"


def _token_from_payload(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    candidates = [
        payload.get("authtoken"),
        payload.get("authToken"),
        payload.get("AuthToken"),
        payload.get("token"),
    ]
    data = payload.get("data")
    if isinstance(data, dict):
        candidates.extend([
            data.get("authtoken"),
            data.get("authToken"),
            data.get("AuthToken"),
            data.get("token"),
        ])
    return next((str(value) for value in candidates if value), "")


def request_otp(gstin: str, username: str, client: GSTReturnAPIClient | None = None) -> GSTAPIResult:
    api = client or GSTReturnAPIClient()
    return api.request("GET", AUTH_PATH, "OTPREQUEST", {
        "action": "OTPREQUEST",
        "gstin": gstin,
        "username": username,
    })


def generate_auth_token(gstin: str, username: str, otp: str, client: GSTReturnAPIClient | None = None) -> GSTAPIResult:
    api = client or GSTReturnAPIClient()
    result = api.request("GET", AUTH_PATH, "AUTHTOKEN", {
        "action": "AUTHTOKEN",
        "gstin": gstin,
        "username": username,
        "OTP": otp,
    })
    if result.success:
        token = _token_from_payload(result.raw)
        if token:
            result.data = {**(result.data if isinstance(result.data, dict) else {}), "authtoken": token}
    return result
