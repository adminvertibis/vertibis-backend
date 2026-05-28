import json
import os
import socket
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.services.gst_return_api.errors import GSTAPIConfigError
from app.services.gst_return_api.models import GSTAPIResult


SENSITIVE_KEYS = {"password", "authtoken", "otp", "aspid"}


def mask_value(value: object, visible: int = 4) -> str:
    text = str(value or "")
    if not text:
        return ""
    if len(text) <= visible * 2:
        return f"{text[:2]}***"
    return f"{text[:visible]}***{text[-visible:]}"


def mask_params(params: dict[str, Any]) -> dict[str, Any]:
    masked = {}
    for key, value in params.items():
        if key.lower() in SENSITIVE_KEYS:
            masked[key] = mask_value(value)
        elif key.lower() == "gstin":
            masked[key] = mask_value(value, 3)
        else:
            masked[key] = value
    return masked


def parse_json(text: str) -> Any:
    if not text:
        return {}
    try:
        data = json.loads(text)
        if isinstance(data, dict) and isinstance(data.get("data"), str):
            try:
                data["data"] = json.loads(data["data"])
            except Exception:
                pass
        return data
    except Exception:
        return {"raw": text}


class GSTReturnAPIClient:
    def __init__(self) -> None:
        self.env = os.getenv("GST_API_ENV", "sandbox").strip().lower()
        self.sandbox_base_url = os.getenv("GST_SANDBOX_BASE_URL", "https://gstsandbox.charteredinfo.com").strip().rstrip("/")
        self.prod_base_url = os.getenv("GST_PROD_BASE_URL", "https://gstapi.charteredinfo.com").strip().rstrip("/")
        self.asp_id = os.getenv("GST_ASP_ID", "").strip()
        self.asp_password = os.getenv("GST_ASP_PASSWORD", "").strip()
        self.timeout_seconds = int(os.getenv("GST_TIMEOUT_SECONDS", "30") or "30")
        self.remote_enabled = os.getenv("GST_API_REMOTE_ENABLED", "true").strip().lower() not in {"0", "false", "no", "off"}

    @property
    def base_url(self) -> str:
        return self.prod_base_url if self.env == "production" else self.sandbox_base_url

    def ensure_config(self) -> None:
        if not self.remote_enabled:
            raise GSTAPIConfigError("GST API remote calls are disabled. Set GST_API_REMOTE_ENABLED=true after configuring ASP credentials.")
        missing = []
        if not self.asp_id:
            missing.append("GST_ASP_ID")
        if not self.asp_password:
            missing.append("GST_ASP_PASSWORD")
        if missing:
            raise GSTAPIConfigError(f"GST API credentials missing: {', '.join(missing)}")

    def provider_params(self) -> dict[str, str]:
        self.ensure_config()
        return {"aspid": self.asp_id, "password": self.asp_password}

    def build_url(self, path: str, params: dict[str, Any]) -> str:
        query = urlencode({key: value for key, value in params.items() if value is not None and value != ""})
        url = f"{self.base_url}/{path.lstrip('/')}"
        return f"{url}?{query}" if query else url

    def request(self, method: str, path: str, action: str, params: dict[str, Any], body: Any = None) -> GSTAPIResult:
        safe_params = {**self.provider_params(), **params}
        url = self.build_url(path, safe_params)
        body_bytes = None
        headers = {}
        if body is not None:
            body_bytes = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"

        try:
            request = Request(url, data=body_bytes, headers=headers, method=method.upper())
            with urlopen(request, timeout=self.timeout_seconds) as response:
                text = response.read().decode("utf-8", errors="replace")
                data = parse_json(text)
                return GSTAPIResult(
                    success=True,
                    data=data.get("data", data) if isinstance(data, dict) else data,
                    raw=data,
                    endpoint=self.build_url(path, mask_params(safe_params)),
                    action=action,
                    status_code=response.status,
                    method=method.upper(),
                )
        except HTTPError as exc:
            text = exc.read().decode("utf-8", errors="replace")
            return GSTAPIResult(
                success=False,
                data={},
                error=f"GST API HTTP {exc.code}: {text[:240]}",
                raw=parse_json(text),
                endpoint=self.build_url(path, mask_params(safe_params)),
                action=action,
                status_code=exc.code,
                method=method.upper(),
            )
        except (URLError, TimeoutError, socket.timeout) as exc:
            return GSTAPIResult(
                success=False,
                data={},
                error=f"GST API unavailable: {exc}",
                raw={},
                endpoint=self.build_url(path, mask_params(safe_params)),
                action=action,
                status_code=None,
                method=method.upper(),
            )
