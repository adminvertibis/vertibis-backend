from app.services.gst_return_api.client import GSTReturnAPIClient
from app.services.gst_return_api.models import GSTAPIResult


GSTR3B_SUMMARY_PATH = "/taxpayerapi/dec/v0.3/returns/gstr3b"
GSTR3B_AUTOLIAB_PATH = "/taxpayerapi/dec/v3.0/returns/gstr3b"


def _base_params(gstin: str, username: str, authtoken: str, ret_period: str) -> dict[str, str]:
    return {
        "gstin": gstin,
        "username": username,
        "authtoken": authtoken,
        "ret_period": ret_period,
    }


def get_gstr3b_summary(gstin: str, username: str, authtoken: str, ret_period: str, client: GSTReturnAPIClient | None = None) -> GSTAPIResult:
    api = client or GSTReturnAPIClient()
    return api.request("GET", GSTR3B_SUMMARY_PATH, "RETSUM", {
        **_base_params(gstin, username, authtoken, ret_period),
        "action": "RETSUM",
    })


def get_gstr3b_auto_liability(gstin: str, username: str, authtoken: str, ret_period: str, client: GSTReturnAPIClient | None = None) -> GSTAPIResult:
    api = client or GSTReturnAPIClient()
    return api.request("GET", GSTR3B_AUTOLIAB_PATH, "AUTOLIAB", {
        **_base_params(gstin, username, authtoken, ret_period),
        "action": "AUTOLIAB",
    })
