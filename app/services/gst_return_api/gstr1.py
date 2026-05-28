from app.services.gst_return_api.client import GSTReturnAPIClient
from app.services.gst_return_api.models import GSTAPIResult


GSTR1_PATH = "/taxpayerapi/dec/v2.1/returns/gstr1"


def _base_params(gstin: str, username: str, authtoken: str, ret_period: str) -> dict[str, str]:
    return {
        "gstin": gstin,
        "username": username,
        "authtoken": authtoken,
        "ret_period": ret_period,
    }


def get_gstr1_b2b(gstin: str, username: str, authtoken: str, ret_period: str, client: GSTReturnAPIClient | None = None) -> GSTAPIResult:
    api = client or GSTReturnAPIClient()
    return api.request("GET", GSTR1_PATH, "B2B", {
        **_base_params(gstin, username, authtoken, ret_period),
        "action": "B2B",
    })


def get_gstr1_summary(gstin: str, username: str, authtoken: str, ret_period: str, client: GSTReturnAPIClient | None = None) -> GSTAPIResult:
    api = client or GSTReturnAPIClient()
    return api.request("GET", GSTR1_PATH, "RETSUM", {
        **_base_params(gstin, username, authtoken, ret_period),
        "action": "RETSUM",
        "smrytyp": "L",
    })
