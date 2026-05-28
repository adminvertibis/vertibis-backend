"""
Data extraction from uploaded GST, ITR, and banking files.
Supports GST portal PDFs for GSTR-1/GSTR-3B and JSON for GSTR-2B/ITR.
"""

import csv
import json
import re
from datetime import datetime
from io import BytesIO, StringIO
from typing import Any, Dict, Optional

try:
    from pypdf import PdfReader
except Exception:  # pragma: no cover - dependency is installed in production requirements
    PdfReader = None


class DataExtractor:
    @staticmethod
    def content_to_text(content: bytes, filename: str) -> str:
        if filename.lower().endswith(".pdf") and PdfReader is not None:
            try:
                reader = PdfReader(BytesIO(content))
                return "\n".join(page.extract_text() or "" for page in reader.pages)
            except Exception:
                return ""
        return content.decode("utf-8", errors="replace")

    @staticmethod
    def extract_all(files_dict: Dict[str, str], fy_year: str) -> Dict[str, Any]:
        extracted: Dict[str, Any] = {}

        if files_dict.get("gstr1"):
            extracted.update(DataExtractor._extract_gstr1(files_dict["gstr1"]))
        if files_dict.get("gstr3b"):
            extracted.update(DataExtractor._extract_gstr3b(files_dict["gstr3b"]))
        if files_dict.get("gstr2a"):
            extracted.update(DataExtractor._extract_gstr2a(files_dict["gstr2a"]))
        if files_dict.get("itr"):
            extracted.update(DataExtractor._extract_itr(files_dict["itr"]))
        if files_dict.get("banking"):
            extracted.update(DataExtractor._extract_banking(files_dict["banking"]))

        extracted["data_completeness_pct"] = DataExtractor._calculate_completeness(extracted)
        extracted["fy_year"] = fy_year
        return extracted

    @staticmethod
    def _amount(value: str | None) -> float:
        if not value:
            return 0.0
        cleaned = re.sub(r"[^0-9.-]", "", value)
        try:
            return float(cleaned) if cleaned not in ("", "-", ".") else 0.0
        except ValueError:
            return 0.0

    @staticmethod
    def _first_amount_after(text: str, anchor: str, max_chars: int = 900) -> float:
        idx = text.lower().find(anchor.lower())
        if idx < 0:
            return 0.0
        window = text[idx:idx + max_chars]
        match = re.search(r"Total\s+\d+\s+\w+\s+([0-9,]+(?:\.\d{2})?)", window, re.I)
        if match:
            return DataExtractor._amount(match.group(1))
        match = re.search(r"([0-9,]+(?:\.\d{2})?)", window)
        return DataExtractor._amount(match.group(1) if match else None)

    @staticmethod
    def _parse_period_date(text: str, default_day: int) -> Optional[datetime]:
        month_match = re.search(r"(?:Tax period|Period)\s+([A-Za-z]+)", text, re.I)
        year_match = re.search(r"(?:Financial year|Year)\s+(\d{4})-\d{2}", text, re.I)
        if month_match and year_match:
            try:
                month = datetime.strptime(month_match.group(1)[:3], "%b").month
                return datetime(int(year_match.group(1)), month, default_day)
            except ValueError:
                pass
        return None

    @staticmethod
    def _parse_date(date_str: str | None) -> Optional[datetime]:
        if not date_str:
            return None
        formats = ["%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d", "%d.%m.%Y"]
        for fmt in formats:
            try:
                return datetime.strptime(date_str.strip(), fmt)
            except ValueError:
                continue
        return None

    @staticmethod
    def _extract_gstr1(content: str) -> Dict[str, Any]:
        try:
            data = json.loads(content)
            return {
                "gstr1_filing_date": DataExtractor._parse_date(data.get("filing_date")),
                "gstr1_total_sales": float(data.get("total_taxable_supplies", 0) or 0),
                "gstr1_itc_claimed": float(data.get("total_itc_claimed", 0) or 0),
                "gstr1_amendments_count": int(data.get("amendments_count", 0) or 0),
            }
        except Exception:
            pass

        arn_date = re.search(r"ARN date\s+(\d{2}/\d{2}/\d{4})", content, re.I)
        taxable_sales = DataExtractor._first_amount_after(content, "4A - Taxable outward supplies")
        exempt_sales = DataExtractor._first_amount_after(content, "8 - Nil rated, exempted and non GST outward supplies", 500)
        return {
            "gstr1_filing_date": DataExtractor._parse_date(arn_date.group(1) if arn_date else None) or DataExtractor._parse_period_date(content, 11),
            "gstr1_total_sales": taxable_sales + exempt_sales,
            "gstr1_taxable_sales": taxable_sales,
            "gstr1_exempt_sales": exempt_sales,
            "gstr1_itc_claimed": 0.0,
            "gstr1_amendments_count": len(re.findall(r"Amend", content, re.I)),
        }

    @staticmethod
    def _extract_gstr3b(content: str) -> Dict[str, Any]:
        try:
            data = json.loads(content)
            return {
                "gstr3b_filing_date": DataExtractor._parse_date(data.get("filing_date")),
                "gstr3b_total_sales": float(data.get("total_sales", 0) or 0),
                "gstr3b_itc_availed": float(data.get("total_itc_availed", 0) or 0),
                "gstr3b_gst_payment": float(data.get("gst_payment", 0) or 0),
            }
        except Exception:
            pass

        arn_date = re.search(r"Date of ARN\s+(\d{2}/\d{2}/\d{4})", content, re.I)
        outward = re.search(r"\(a\)\s+Outward taxable supplies.*?\n\s*([0-9,]+(?:\.\d{2})?)\s+([0-9,]+(?:\.\d{2})?)\s+([0-9,]+(?:\.\d{2})?)\s+([0-9,]+(?:\.\d{2})?)", content, re.I | re.S)
        net_itc = re.search(r"C\.\s+Net ITC available \(A-B\)\s+([0-9,]+(?:\.\d{2})?)\s+([0-9,]+(?:\.\d{2})?)\s+([0-9,]+(?:\.\d{2})?)", content, re.I)
        cash_paid = re.findall(r"\b(?:Integrated\s+tax|Central\s+tax|State/UT\s+tax)\s+[0-9,]+(?:\.\d{2})?.*?\s([0-9,]+(?:\.\d{2})?)\s+0\.00", content, re.I)
        return {
            "gstr3b_filing_date": DataExtractor._parse_date(arn_date.group(1) if arn_date else None) or DataExtractor._parse_period_date(content, 20),
            "gstr3b_total_sales": DataExtractor._amount(outward.group(1) if outward else None),
            "gstr3b_itc_availed": sum(DataExtractor._amount(net_itc.group(i)) for i in range(1, 4)) if net_itc else 0.0,
            "gstr3b_gst_payment": sum(DataExtractor._amount(value) for value in cash_paid),
        }

    @staticmethod
    def _sum_tax_values(node: Any) -> float:
        tax_keys = {"igst", "cgst", "sgst", "cess"}
        if isinstance(node, dict):
            direct_tax = sum(float(node.get(key) or 0) for key in tax_keys if key in node)
            if direct_tax:
                return direct_tax
            return sum(DataExtractor._sum_tax_values(value) for value in node.values())
        if isinstance(node, list):
            return sum(DataExtractor._sum_tax_values(value) for value in node)
        return 0.0

    @staticmethod
    def _extract_gstr2a(content: str) -> Dict[str, Any]:
        try:
            data = json.loads(content)
            root = data.get("data", data)
            if "itcsumm" in root or "docdata" in root:
                available = root.get("itcsumm", {}).get("itcavl", {})
                unavailable = root.get("itcsumm", {}).get("itcunavl", {})
                b2b = root.get("docdata", {}).get("b2b", [])
                return {
                    "gstr2a_supplier_count": len(b2b),
                    "gstr2a_itc_received": DataExtractor._sum_tax_values(available),
                    "gstr2a_discrepancies_count": 1 if DataExtractor._sum_tax_values(unavailable) > 0 else 0,
                }
            return {
                "gstr2a_supplier_count": int(data.get("supplier_count", 0) or 0),
                "gstr2a_itc_received": float(data.get("itc_received", 0) or 0),
                "gstr2a_discrepancies_count": int(data.get("discrepancies_count", 0) or 0),
            }
        except Exception:
            return {}

    @staticmethod
    def _extract_itr(content: str) -> Dict[str, Any]:
        try:
            data = json.loads(content)
            return {
                "itr_filing_date": DataExtractor._parse_date(data.get("filing_date")),
                "itr_total_turnover": float(data.get("total_turnover", 0) or 0),
                "itr_net_profit": float(data.get("net_profit", 0) or 0),
                "itr_profit_margin_pct": float(data.get("profit_margin_pct", 0) or 0),
            }
        except Exception:
            return {}

    @staticmethod
    def _extract_banking(content: str) -> Dict[str, Any]:
        try:
            csv_reader = csv.DictReader(StringIO(content))
            balances = []
            bounces = 0
            for row in csv_reader:
                try:
                    balances.append(float(row.get("balance", 0) or 0))
                    bounces += int(row.get("bounce_count", 0) or 0)
                except Exception:
                    continue
            return {
                "banking_min_balance": min(balances) if balances else 0,
                "banking_avg_balance": sum(balances) / len(balances) if balances else 0,
                "banking_bounce_count": bounces,
            }
        except Exception:
            return {}

    @staticmethod
    def _calculate_completeness(data: Dict[str, Any]) -> float:
        checks = [
            ("GST sales/API signal", any(data.get(field) for field in ("gstr1_total_sales", "gstr3b_total_sales", "gst_return_api_signal_available"))),
            ("GST filing/API status", any(data.get(field) for field in ("gstr1_filing_date", "gstr3b_filing_date", "gst_return_api_signal_available"))),
            ("ITR filing", bool(data.get("itr_filing_date"))),
            ("ITR profit", bool(data.get("itr_net_profit"))),
            ("Banking balance", bool(data.get("banking_avg_balance"))),
        ]
        filled = sum(1 for _, present in checks if present)
        return (filled / len(checks)) * 100
