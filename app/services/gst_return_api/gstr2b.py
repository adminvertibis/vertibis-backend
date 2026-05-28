from app.services.gst_return_api.client import GSTReturnAPIClient
from app.services.gst_return_api.models import GSTAPIResult


GSTR2B_PATH = "/taxpayerapi/dec/v1.0/returns/gstr2b"


def get_gstr2b(gstin: str, username: str, authtoken: str, ret_period: str, client: GSTReturnAPIClient | None = None) -> GSTAPIResult:
    api = client or GSTReturnAPIClient()
    return api.request("GET", GSTR2B_PATH, "GET2B", {
        "action": "GET2B",
        "gstin": gstin,
        "username": username,
        "authtoken": authtoken,
        "ret_period": ret_period,
        "rtnprd": ret_period,
    })
