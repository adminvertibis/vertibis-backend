import os
import unittest

from app.services.gst_return_api.client import GSTReturnAPIClient, mask_params
from app.services.gst_return_api.normalizers import normalize_gstr1, normalize_gstr2b, normalize_gstr3b


class GSTReturnAPIClientTests(unittest.TestCase):
    def setUp(self):
        os.environ["GST_API_ENV"] = "sandbox"
        os.environ["GST_SANDBOX_BASE_URL"] = "https://gstsandbox.charteredinfo.com"
        os.environ["GST_ASP_ID"] = "testasp"
        os.environ["GST_ASP_PASSWORD"] = "testpassword"

    def test_build_url_uses_sandbox_base_and_query_params(self):
        client = GSTReturnAPIClient()
        url = client.build_url(
            "/taxpayerapi/dec/v2.1/returns/gstr1",
            {
                "action": "RETSUM",
                "gstin": "33AANCS2882A1ZG",
                "ret_period": "032025",
            },
        )

        self.assertTrue(url.startswith("https://gstsandbox.charteredinfo.com/taxpayerapi/dec/v2.1/returns/gstr1?"))
        self.assertIn("action=RETSUM", url)
        self.assertIn("ret_period=032025", url)

    def test_mask_params_hides_credentials_and_partly_masks_gstin(self):
        masked = mask_params(
            {
                "aspid": "testasp",
                "password": "testpassword",
                "authtoken": "secret-token",
                "gstin": "33AANCS2882A1ZG",
                "action": "GET2B",
            }
        )

        self.assertNotEqual(masked["password"], "testpassword")
        self.assertNotEqual(masked["authtoken"], "secret-token")
        self.assertTrue(str(masked["gstin"]).startswith("33A"))
        self.assertEqual(masked["action"], "GET2B")


class GSTReturnNormalizerTests(unittest.TestCase):
    def test_normalize_gstr1_b2b_payload(self):
        normalized = normalize_gstr1(
            "33AANCS2882A1ZG",
            "032025",
            {
                "B2B": {
                    "b2b": [
                        {
                            "ctin": "33AAAAA0000A1Z5",
                            "inv": [
                                {
                                    "inum": "S-1",
                                    "itms": [
                                        {"itm_det": {"txval": 1000, "iamt": 180}},
                                        {"itm_det": {"txval": 500, "camt": 45, "samt": 45}},
                                    ],
                                }
                            ],
                        }
                    ]
                }
            },
        )

        self.assertEqual(normalized["invoice_count"], 1)
        self.assertEqual(normalized["unique_recipients"], 1)
        self.assertEqual(normalized["b2b_taxable_value"], 1500)
        self.assertEqual(normalized["b2b_tax"], 270)

    def test_normalize_gstr3b_summary_payload(self):
        normalized = normalize_gstr3b(
            "33AANCS2882A1ZG",
            "032025",
            {
                "RETSUM": {
                    "sup_details": {"osup_det": {"txval": 2000, "iamt": 360}},
                    "itc_elg": {"itc_avl": [{"iamt": 120, "camt": 30, "samt": 30}]},
                    "intr_ltfee": {"intr": 10, "fee": 5},
                }
            },
        )

        self.assertEqual(normalized["outward_taxable_value"], 2000)
        self.assertGreater(normalized["output_tax"], 0)
        self.assertGreater(normalized["eligible_itc"], 0)
        self.assertEqual(normalized["interest"], 10)
        self.assertEqual(normalized["late_fee"], 5)

    def test_normalize_gstr2b_payload(self):
        normalized = normalize_gstr2b(
            "33AANCS2882A1ZG",
            "032025",
            {
                "GET2B": {
                    "docdata": {
                        "b2b": [
                            {
                                "ctin": "33BBBBB0000B1Z5",
                                "inv": [{"inum": "P-1", "iamt": 100, "camt": 20, "samt": 20}],
                            }
                        ]
                    }
                }
            },
        )

        self.assertEqual(normalized["supplier_count"], 1)
        self.assertEqual(normalized["invoice_count"], 1)
        self.assertGreater(normalized["eligible_itc"], 0)
        self.assertEqual(normalized["top_suppliers"][0]["gstin"], "33BBBBB0000B1Z5")


if __name__ == "__main__":
    unittest.main()

