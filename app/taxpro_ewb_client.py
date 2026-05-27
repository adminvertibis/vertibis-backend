import json
import os
import socket
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class TaxProEWBConfigError(RuntimeError):
    pass


class TaxProEWBRemoteError(RuntimeError):
    pass


@dataclass
class TaxProResponse:
    status_code: int
    server_url: str
    payload: Any
    raw_text: str


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _truthy(value: str) -> bool:
    return value.lower() in {"1", "true", "yes", "on"}


def _join_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def _parse_payload(text: str) -> Any:
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


def _number(value: Any) -> float:
    if value is None:
        return 0.0
    try:
        return float(str(value).replace(",", "").strip())
    except Exception:
        return 0.0


def _first_present(record: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if record.get(key) is not None:
            return record.get(key)
    return None


def normalize_eway_date(value: str | None) -> str:
    value = str(value or "").strip()
    if not value:
        return ""
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(value, fmt).strftime("%d/%m/%Y")
        except ValueError:
            continue
    return value


def _collect_eway_records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        records: list[dict[str, Any]] = []
        for item in payload:
            records.extend(_collect_eway_records(item))
        return records

    if not isinstance(payload, dict):
        return []

    if any(key in payload for key in ("ewbNo", "ewayBillNo", "docNo", "ewayBillDate")):
        return [payload]

    records = []
    for key in ("data", "result", "results", "ewayBills", "EwayBills", "ewbList", "billLists"):
        value = payload.get(key)
        if value is not None:
            records.extend(_collect_eway_records(value))
    return records


def summarize_eway_payload(payload: Any) -> dict[str, Any]:
    records = _collect_eway_records(payload)
    total_invoice_value = 0.0
    taxable_value = 0.0
    active_count = 0
    cancelled_count = 0
    rejected_count = 0

    for record in records:
        total_invoice_value += _number(_first_present(record, ("totInvValue", "totalInvoiceValue", "tot_inv_value")))
        taxable_value += _number(_first_present(record, ("totalValue", "taxableAmount", "taxableValue")))
        status = str(record.get("status") or record.get("ewbStatus") or "").upper()
        reject_status = str(record.get("rejectStatus") or "").upper()
        if status in {"ACT", "ACTIVE"}:
            active_count += 1
        if status in {"CNL", "CANCELLED", "CANCEL"}:
            cancelled_count += 1
        if reject_status == "Y":
            rejected_count += 1

    return {
        "ewb_document_count": len(records),
        "ewb_active_count": active_count,
        "ewb_cancelled_count": cancelled_count,
        "ewb_rejected_count": rejected_count,
        "ewb_total_invoice_value": round(total_invoice_value, 2),
        "ewb_taxable_value": round(taxable_value, 2),
    }


class TaxProEWBClient:
    """Small TaxPro/CharteredInfo EWB client with production backup URL support."""

    def __init__(self) -> None:
        self.mode = _env("TAXPRO_EWB_MODE", "sandbox").lower()
        self.remote_enabled = _truthy(_env("TAXPRO_EWB_REMOTE_ENABLED", "false"))
        self.timeout_seconds = int(_env("TAXPRO_EWB_TIMEOUT_SECONDS", "20") or "20")

    def is_remote_enabled(self) -> bool:
        return self.remote_enabled

    def _base_urls(self) -> list[str]:
        if self.mode == "production":
            urls = [
                _env("TAXPRO_EWB_PRIMARY_BASE_URL", "https://einvapi.charteredinfo.com/v1.03/dec"),
                _env("TAXPRO_EWB_BACKUP1_BASE_URL", "https://einvapimum1.charteredinfo.com/v1.03/dec"),
                _env("TAXPRO_EWB_BACKUP2_BASE_URL", "https://einvapidel2.charteredinfo.com/v1.03/dec"),
            ]
        else:
            urls = [_env("TAXPRO_EWB_SANDBOX_BASE_URL", "https://gstsandbox.charteredinfo.com/ewaybillapi/dec/v1.03")]
        return [url.rstrip("/") for url in urls if url]

    def _credentials(self, gstin: str) -> dict[str, str]:
        creds = {
            "aspid": _env("TAXPRO_EWB_ASP_ID"),
            "password": _env("TAXPRO_EWB_ASP_PASSWORD"),
            "gstin": gstin or _env("TAXPRO_EWB_GSTIN"),
            "username": _env("TAXPRO_EWB_USERNAME"),
            "ewbpwd": _env("TAXPRO_EWB_PASSWORD"),
        }
        missing = [key for key, value in creds.items() if not value]
        if missing:
            raise TaxProEWBConfigError(f"TaxPro EWB credentials missing: {', '.join(missing)}")
        return creds

    def _request(self, method: str, path: str, params: dict[str, Any], headers: dict[str, str] | None = None, body: Any = None) -> TaxProResponse:
        body_bytes = None
        request_headers = dict(headers or {})
        if body is not None:
            body_bytes = json.dumps(body).encode("utf-8")
            request_headers["Content-Type"] = "application/json"

        last_error = ""
        for base_url in self._base_urls():
            query = urlencode({key: value for key, value in params.items() if value is not None})
            url = _join_url(base_url, path)
            if query:
                url = f"{url}?{query}"
            try:
                request = Request(url, data=body_bytes, headers=request_headers, method=method.upper())
                with urlopen(request, timeout=self.timeout_seconds) as response:
                    text = response.read().decode("utf-8", errors="replace")
                    return TaxProResponse(response.status, base_url, _parse_payload(text), text)
            except HTTPError as exc:
                text = exc.read().decode("utf-8", errors="replace")
                if 400 <= exc.code < 500:
                    raise TaxProEWBRemoteError(f"TaxPro EWB API returned HTTP {exc.code}: {text[:240]}")
                last_error = f"HTTP {exc.code}: {text[:240]}"
            except (URLError, TimeoutError, socket.timeout) as exc:
                last_error = str(exc)

        raise TaxProEWBRemoteError(f"TaxPro EWB API unavailable after backup URL retry: {last_error}")

    def access_token(self, gstin: str) -> tuple[str, TaxProResponse]:
        creds = self._credentials(gstin)
        params = {"action": "ACCESSTOKEN"}
        headers: dict[str, str] = {}
        if self.mode == "sandbox":
            params.update(creds)
        else:
            headers.update({
                "aspid": creds["aspid"],
                "password": creds["password"],
                "Gstin": creds["gstin"],
                "gstin": creds["gstin"],
                "username": creds["username"],
                "user_name": creds["username"],
                "ewbPwd": creds["ewbpwd"],
                "ewbpwd": creds["ewbpwd"],
            })

        response = self._request("GET", "/auth", params, headers=headers)
        token = self._extract_token(response.payload)
        if not token:
            raise TaxProEWBRemoteError("TaxPro EWB auth response did not include an auth token.")
        return token, response

    def _extract_token(self, payload: Any) -> str:
        if not isinstance(payload, dict):
            return ""
        candidates = [
            payload.get("authtoken"),
            payload.get("authToken"),
            payload.get("AuthToken"),
            payload.get("token"),
            payload.get("access_token"),
        ]
        data = payload.get("data")
        if isinstance(data, dict):
            candidates.extend([
                data.get("authtoken"),
                data.get("authToken"),
                data.get("AuthToken"),
                data.get("token"),
                data.get("access_token"),
            ])
        return next((str(value) for value in candidates if value), "")

    def get_eway_bills_by_date(self, gstin: str, token: str, date_text: str) -> TaxProResponse:
        creds = self._credentials(gstin)
        params = {
            "action": "GetEwayBillsByDate",
            "date": normalize_eway_date(date_text),
        }
        headers: dict[str, str] = {}
        if self.mode == "sandbox":
            params.update({
                "aspid": creds["aspid"],
                "password": creds["password"],
                "gstin": creds["gstin"],
                "authtoken": token,
            })
        else:
            headers.update({
                "aspid": creds["aspid"],
                "password": creds["password"],
                "gstin": creds["gstin"],
                "Gstin": creds["gstin"],
                "authtoken": token,
            })
        return self._request("GET", "/ewayapi", params, headers=headers)

    def fetch_report_signal(self, gstin: str, date_text: str | None = None) -> dict[str, Any]:
        token, auth_response = self.access_token(gstin)
        summary = {
            "ewb_document_count": 0,
            "ewb_active_count": 0,
            "ewb_cancelled_count": 0,
            "ewb_rejected_count": 0,
            "ewb_total_invoice_value": 0,
            "ewb_taxable_value": 0,
        }
        data_response: TaxProResponse | None = None
        if date_text:
            data_response = self.get_eway_bills_by_date(gstin, token, date_text)
            summary = summarize_eway_payload(data_response.payload)

        return {
            "provider": "taxpro_charteredinfo",
            "mode": self.mode,
            "auth_server": auth_response.server_url,
            "data_server": data_response.server_url if data_response else auth_response.server_url,
            "remote_status": "authenticated" if data_response is None else "fetched",
            "fetched_at": datetime.utcnow().isoformat(),
            "summary": summary,
        }
