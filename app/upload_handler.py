import json
import csv
from datetime import datetime
from typing import Dict, List, Tuple, Any
from uuid import UUID
import os

class FileValidator:
    """Validates and extracts data from uploaded files"""
    
    REQUIRED_FIELDS = {
        "gstr1": ["filing_date", "total_taxable_supplies", "total_itc_claimed"],
        "gstr3b": ["filing_date", "total_sales", "total_itc_availed", "gst_payment_amount"],
        "gstr2a": ["supplier_invoices_count", "total_itc_received_from_suppliers"],
        "itr": ["filing_date", "total_turnover", "net_profit"],
        "banking": ["transaction_date", "deposit_amount"],
    }
    
    @staticmethod
    def validate_json(file_content: str, file_type: str) -> Tuple[bool, Dict[str, Any], List[str]]:
        """Validate and extract JSON file"""
        errors = []
        try:
            data = json.loads(file_content)
            
            # Check required fields
            required = FileValidator.REQUIRED_FIELDS.get(file_type, [])
            for field in required:
                if field not in data:
                    errors.append(f"{file_type.upper()}: Missing field '{field}'")
            
            return len(errors) == 0, data, errors
        except json.JSONDecodeError as e:
            return False, {}, [f"JSON parse error: {str(e)}"]
    
    @staticmethod
    def validate_csv(file_content: str, file_type: str) -> Tuple[bool, List[Dict], List[str]]:
        """Validate and extract CSV file (for banking data)"""
        errors = []
        try:
            lines = file_content.strip().split('\n')
            if not lines:
                return False, [], ["CSV file is empty"]
            
            reader = csv.DictReader(lines)
            data = list(reader)
            
            if not data:
                return False, [], ["CSV has no rows"]
            
            # Check required fields
            required = FileValidator.REQUIRED_FIELDS.get(file_type, [])
            for field in required:
                if field not in data[0]:
                    errors.append(f"{file_type.upper()}: Missing field '{field}'")
            
            return len(errors) == 0, data, errors
        except Exception as e:
            return False, [], [f"CSV parse error: {str(e)}"]
    
    @staticmethod
    def extract_gstr1(data: Dict) -> Dict:
        """Extract GSTR-1 fields"""
        return {
            "gstr1_filing_date": data.get("filing_date"),
            "gstr1_total_supplies": float(data.get("total_taxable_supplies", 0)),
            "gstr1_itc_claimed": float(data.get("total_itc_claimed", 0)),
            "gstr1_amendments_count": int(data.get("document_amendments_count", 0)),
        }
    
    @staticmethod
    def extract_gstr3b(data: Dict) -> Dict:
        """Extract GSTR-3B fields"""
        return {
            "gstr3b_filing_date": data.get("filing_date"),
            "gstr3b_total_sales": float(data.get("total_sales", 0)),
            "gstr3b_itc_availed": float(data.get("total_itc_availed", 0)),
            "gstr3b_gst_payment": float(data.get("gst_payment_amount", 0)),
            "gstr3b_is_on_time": data.get("is_filed_on_time", False),
        }
    
    @staticmethod
    def extract_gstr2a(data: Dict) -> Dict:
        """Extract GSTR-2A fields"""
        return {
            "gstr2a_supplier_count": int(data.get("supplier_invoices_count", 0)),
            "gstr2a_itc_received": float(data.get("total_itc_received_from_suppliers", 0)),
            "gstr2a_discrepancies": int(data.get("discrepancies_noticed_count", 0)),
        }
    
    @staticmethod
    def extract_itr(data: Dict) -> Dict:
        """Extract ITR fields"""
        turnover = float(data.get("total_turnover", 0))
        profit = float(data.get("net_profit", 0))
        profit_margin = (profit / turnover * 100) if turnover > 0 else 0
        
        return {
            "itr_filing_date": data.get("filing_date"),
            "itr_total_turnover": turnover,
            "itr_net_profit": profit,
            "itr_profit_margin_pct": profit_margin,
        }
    
    @staticmethod
    def extract_banking(data_list: List[Dict]) -> Dict:
        """Extract Banking fields from CSV"""
        if not data_list:
            return {}
        
        balances = []
        total_deposits = 0
        bounce_count = 0
        
        for row in data_list:
            try:
                balance = float(row.get("monthly_balance_avg", 0))
                balances.append(balance)
                total_deposits += float(row.get("deposit_amount", 0))
                bounce_count += int(row.get("bounce_count", 0))
            except (ValueError, TypeError):
                continue
        
        avg_balance = sum(balances) / len(balances) if balances else 0
        min_balance = min(balances) if balances else 0
        
        return {
            "banking_avg_balance": avg_balance,
            "banking_min_balance": min_balance,
            "banking_bounce_count": bounce_count,
            "banking_deposits_total": total_deposits,
        }

class UploadProcessor:
    """Process uploaded files and store in database"""
    
    @staticmethod
    def process_upload(client_id: UUID, fy_year: str, files: Dict[str, str]) -> Tuple[str, Dict[str, Any], List[str]]:
        """
        Process uploaded files
        Returns: (status, extracted_data, errors)
        """
        validator = FileValidator()
        extracted_data = {}
        errors = []
        uploaded_files = []
        missing_files = []
        
        file_types = ["gstr1", "gstr3b", "gstr2a", "itr", "banking"]
        
        for file_type in file_types:
            if file_type not in files:
                missing_files.append(file_type)
                continue
            
            file_content = files[file_type]
            is_valid = False
            data = None
            
            # JSON files
            if file_type in ["gstr1", "gstr3b", "gstr2a", "itr"]:
                is_valid, data, file_errors = validator.validate_json(file_content, file_type)
                errors.extend(file_errors)
                
                if is_valid:
                    # Extract specific fields
                    if file_type == "gstr1":
                        extracted_data.update(validator.extract_gstr1(data))
                    elif file_type == "gstr3b":
                        extracted_data.update(validator.extract_gstr3b(data))
                    elif file_type == "gstr2a":
                        extracted_data.update(validator.extract_gstr2a(data))
                    elif file_type == "itr":
                        extracted_data.update(validator.extract_itr(data))
                    uploaded_files.append(file_type)
            
            # CSV file (banking)
            elif file_type == "banking":
                is_valid, data, file_errors = validator.validate_csv(file_content, file_type)
                errors.extend(file_errors)
                
                if is_valid:
                    extracted_data.update(validator.extract_banking(data))
                    uploaded_files.append(file_type)
        
        # Calculate data completeness
        total_fields = 13  # Total data fields across all files
        available_fields = len([v for v in extracted_data.values() if v is not None and v != 0])
        completeness_pct = (available_fields / total_fields) * 100
        extracted_data["data_completeness_pct"] = completeness_pct
        
        # Determine overall status
        if len(uploaded_files) == 5:
            status = "complete"
        elif len(uploaded_files) > 0:
            status = "partial"
        else:
            status = "error"
        
        return status, extracted_data, errors, uploaded_files, missing_files

    @staticmethod
    def store_in_database(client_id: UUID, upload_id: UUID, fy_year: str, extracted_data: Dict, status: str) -> UUID:
        """Store extracted data in database and return client_data_id"""
        from database import execute_insert
        
        # Build insert query
        fields = []
        values = []
        params = []
        
        # Add fixed fields
        fields.extend(["id", "client_id", "upload_id", "fy_year"])
        values.extend(["gen_random_uuid()", "%s", "%s", "%s"])
        params.extend([client_id, upload_id, fy_year])
        
        # Add extracted data fields
        for key, value in extracted_data.items():
            if key not in ["data_completeness_pct"]:  # Will add separately
                fields.append(key)
                values.append("%s")
                params.append(value)
        
        # Add completeness and timestamps
        fields.extend(["data_completeness_pct", "data_recency_days", "created_at", "updated_at"])
        values.extend(["%s", "%s", "CURRENT_TIMESTAMP", "CURRENT_TIMESTAMP"])
        params.extend([extracted_data.get("data_completeness_pct", 0), 0])
        
        query = f"INSERT INTO client_data ({', '.join(fields)}) VALUES ({', '.join(values)}) RETURNING id"
        
        result = execute_insert(query, tuple(params))
        return result["id"] if result else None
