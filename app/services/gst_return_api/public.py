from app.services.gst_return_api.client import GSTReturnAPIClient
from app.services.gst_return_api.models import GSTAPIResult


def get_return_track(gstin: str, financial_year: str, client: GSTReturnAPIClient | None = None) -> GSTAPIResult:
    api = client or GSTReturnAPIClient()
    return api.request("GET", "/commonapi/v1.0/returns", "RETTRACK", {
        "Action": "RETTRACK",
        "Gstin": gstin,
        "fy": financial_year,
    })


def search_gstin(gstin: str, client: GSTReturnAPIClient | None = None) -> GSTAPIResult:
    api = client or GSTReturnAPIClient()
    return api.request("GET", "/commonapi/v1.1/search", "TP", {
        "action": "TP",
        "Gstin": gstin,
    })
