from collections import defaultdict
from typing import Any


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _number(value: Any) -> float:
    try:
        return float(str(value or 0).replace(",", "").strip() or 0)
    except Exception:
        return 0.0


def _root(payload: Any) -> Any:
    if isinstance(payload, dict) and "data" in payload:
        return payload["data"]
    return payload


def _recursive_sum(node: Any, keys: set[str]) -> float:
    if isinstance(node, dict):
        total = sum(_number(value) for key, value in node.items() if key in keys)
        return total + sum(_recursive_sum(value, keys) for value in node.values() if isinstance(value, (dict, list)))
    if isinstance(node, list):
        return sum(_recursive_sum(value, keys) for value in node)
    return 0.0


def _recursive_count_key(node: Any, keys: set[str]) -> int:
    if isinstance(node, dict):
        count = sum(1 for key, value in node.items() if key in keys and value)
        return count + sum(_recursive_count_key(value, keys) for value in node.values() if isinstance(value, (dict, list)))
    if isinstance(node, list):
        return sum(_recursive_count_key(value, keys) for value in node)
    return 0


def _sum_children_for_parent_keys(node: Any, parent_keys: set[str], child_keys: set[str]) -> float:
    if isinstance(node, dict):
        total = 0.0
        for key, value in node.items():
            if key in parent_keys:
                total += _number(value) if not isinstance(value, (dict, list)) else _recursive_sum(value, child_keys)
            elif isinstance(value, (dict, list)):
                total += _sum_children_for_parent_keys(value, parent_keys, child_keys)
        return total
    if isinstance(node, list):
        return sum(_sum_children_for_parent_keys(value, parent_keys, child_keys) for value in node)
    return 0.0


def normalize_gstr1(gstin: str, period: str, raw_sections: dict[str, Any]) -> dict[str, Any]:
    b2b_payload = _root(raw_sections.get("B2B") or raw_sections.get("b2b") or raw_sections)
    b2b_rows = []
    if isinstance(b2b_payload, dict):
        b2b_rows = _as_list(b2b_payload.get("b2b") or b2b_payload.get("B2B"))
    elif isinstance(b2b_payload, list):
        b2b_rows = b2b_payload

    invoice_count = 0
    recipients: set[str] = set()
    taxable_value = 0.0
    tax_value = 0.0
    for party in b2b_rows:
        if not isinstance(party, dict):
            continue
        if party.get("ctin"):
            recipients.add(str(party.get("ctin")))
        for invoice in _as_list(party.get("inv")):
            if not isinstance(invoice, dict):
                continue
            invoice_count += 1
            for item in _as_list(invoice.get("itms")):
                detail = item.get("itm_det") if isinstance(item, dict) else None
                if not isinstance(detail, dict):
                    continue
                taxable_value += _number(detail.get("txval"))
                tax_value += _number(detail.get("iamt")) + _number(detail.get("camt")) + _number(detail.get("samt")) + _number(detail.get("csamt"))

    if taxable_value == 0:
        taxable_value = _recursive_sum(raw_sections, {"txval", "taxable_value", "taxableAmount"})
    if tax_value == 0:
        tax_value = _recursive_sum(raw_sections, {"iamt", "camt", "samt", "csamt", "igst", "cgst", "sgst", "cess"})
    if invoice_count == 0:
        invoice_count = _recursive_count_key(raw_sections, {"inum", "invoice_number"})

    return {
        "gstin": gstin,
        "period": period,
        "return_type": "gstr1",
        "b2b_taxable_value": round(taxable_value, 2),
        "b2b_tax": round(tax_value, 2),
        "invoice_count": invoice_count,
        "unique_recipients": len(recipients),
        "raw_sections": raw_sections,
    }


def normalize_gstr3b(gstin: str, period: str, raw_sections: dict[str, Any]) -> dict[str, Any]:
    payload = _root(raw_sections.get("RETSUM") or raw_sections.get("retsum") or raw_sections)
    outward_taxable = _recursive_sum(payload, {"txval", "taxable_value", "taxableAmount"})
    output_tax = _recursive_sum(payload, {"iamt", "camt", "samt", "csamt", "igst", "cgst", "sgst", "cess"})
    eligible_itc = _recursive_sum(payload, {"elg_itc", "itc", "tx_i", "tx_c", "tx_s", "tx_cs"})
    eligible_itc += _sum_children_for_parent_keys(
        payload,
        {"itc_avl", "itc_available", "eligible_itc"},
        {"iamt", "camt", "samt", "csamt", "igst", "cgst", "sgst", "cess", "tx_i", "tx_c", "tx_s", "tx_cs"},
    )
    cash_paid = _recursive_sum(payload, {"cash_paid", "cash", "pd_cash"})
    interest = _recursive_sum(payload, {"intr", "interest"})
    late_fee = _recursive_sum(payload, {"fee", "late_fee"})

    return {
        "gstin": gstin,
        "period": period,
        "return_type": "gstr3b",
        "outward_taxable_value": round(outward_taxable, 2),
        "output_tax": round(output_tax, 2),
        "eligible_itc": round(eligible_itc, 2),
        "cash_paid": round(cash_paid, 2),
        "interest": round(interest, 2),
        "late_fee": round(late_fee, 2),
        "raw_sections": raw_sections,
    }


def normalize_gstr2b(gstin: str, period: str, raw_sections: dict[str, Any]) -> dict[str, Any]:
    payload = _root(raw_sections.get("GET2B") or raw_sections.get("get2b") or raw_sections)
    docdata = payload.get("docdata", payload) if isinstance(payload, dict) else {}
    supplier_totals: dict[str, float] = defaultdict(float)
    invoice_count = 0

    b2b_rows = []
    if isinstance(docdata, dict):
        b2b_rows = _as_list(docdata.get("b2b") or docdata.get("B2B"))
    for supplier in b2b_rows:
        if not isinstance(supplier, dict):
            continue
        supplier_id = str(supplier.get("ctin") or supplier.get("supplier_gstin") or "Unknown")
        invoices = _as_list(supplier.get("inv"))
        invoice_count += len([item for item in invoices if isinstance(item, dict)])
        supplier_totals[supplier_id] += _recursive_sum(invoices, {"iamt", "camt", "samt", "csamt", "tx_i", "tx_c", "tx_s", "tx_cs"})

    eligible_itc = _recursive_sum(payload, {"itcavl", "itc_avl", "iamt", "camt", "samt", "csamt", "tx_i", "tx_c", "tx_s", "tx_cs"})
    top_suppliers = [
        {"gstin": gstin_key, "itc": round(value, 2)}
        for gstin_key, value in sorted(supplier_totals.items(), key=lambda item: item[1], reverse=True)[:10]
    ]

    return {
        "gstin": gstin,
        "period": period,
        "return_type": "gstr2b",
        "eligible_itc": round(eligible_itc, 2),
        "supplier_count": len(supplier_totals),
        "invoice_count": invoice_count or _recursive_count_key(payload, {"inum", "invoice_number"}),
        "top_suppliers": top_suppliers,
        "raw_sections": raw_sections,
    }
