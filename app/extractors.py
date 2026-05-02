"""
Data extraction from uploaded files
Copy this entire content to: C:\vertibis-backend\app\extractors.py
"""

import json
import csv
from datetime import datetime
from typing import Dict, Any, Optional
from io import StringIO


class DataExtractor:
    @staticmethod
    def extract_all(files_dict: Dict[str, str], fy_year: str) -> Dict[str, Any]:
        extracted = {}
        
        if files_dict.get('gstr1'):
            extracted.update(DataExtractor._extract_gstr1(files_dict['gstr1']))
        if files_dict.get('gstr3b'):
            extracted.update(DataExtractor._extract_gstr3b(files_dict['gstr3b']))
        if files_dict.get('gstr2a'):
            extracted.update(DataExtractor._extract_gstr2a(files_dict['gstr2a']))
        if files_dict.get('itr'):
            extracted.update(DataExtractor._extract_itr(files_dict['itr']))
        if files_dict.get('banking'):
            extracted.update(DataExtractor._extract_banking(files_dict['banking']))
        
        extracted['data_completeness_pct'] = DataExtractor._calculate_completeness(extracted)
        extracted['fy_year'] = fy_year
        
        return extracted
    
    @staticmethod
    def _extract_gstr1(json_str: str) -> Dict[str, Any]:
        try:
            data = json.loads(json_str)
            return {
                'gstr1_filing_date': DataExtractor._parse_date(data.get('filing_date')),
                'gstr1_total_sales': float(data.get('total_taxable_supplies', 0)),
                'gstr1_itc_claimed': float(data.get('total_itc_claimed', 0)),
                'gstr1_amendments_count': int(data.get('amendments_count', 0)),
            }
        except:
            return {}
    
    @staticmethod
    def _extract_gstr3b(json_str: str) -> Dict[str, Any]:
        try:
            data = json.loads(json_str)
            return {
                'gstr3b_filing_date': DataExtractor._parse_date(data.get('filing_date')),
                'gstr3b_total_sales': float(data.get('total_sales', 0)),
                'gstr3b_itc_availed': float(data.get('total_itc_availed', 0)),
                'gstr3b_gst_payment': float(data.get('gst_payment', 0)),
            }
        except:
            return {}
    
    @staticmethod
    def _extract_gstr2a(json_str: str) -> Dict[str, Any]:
        try:
            data = json.loads(json_str)
            return {
                'gstr2a_supplier_count': int(data.get('supplier_count', 0)),
                'gstr2a_itc_received': float(data.get('itc_received', 0)),
                'gstr2a_discrepancies_count': int(data.get('discrepancies_count', 0)),
            }
        except:
            return {}
    
    @staticmethod
    def _extract_itr(json_str: str) -> Dict[str, Any]:
        try:
            data = json.loads(json_str)
            return {
                'itr_filing_date': DataExtractor._parse_date(data.get('filing_date')),
                'itr_total_turnover': float(data.get('total_turnover', 0)),
                'itr_net_profit': float(data.get('net_profit', 0)),
                'itr_profit_margin_pct': float(data.get('profit_margin_pct', 0)),
            }
        except:
            return {}
    
    @staticmethod
    def _extract_banking(csv_str: str) -> Dict[str, Any]:
        try:
            csv_reader = csv.DictReader(StringIO(csv_str))
            balances = []
            bounces = 0
            
            for row in csv_reader:
                try:
                    balance = float(row.get('balance', 0))
                    balances.append(balance)
                    bounce = int(row.get('bounce_count', 0))
                    bounces += bounce
                except:
                    continue
            
            min_balance = min(balances) if balances else 0
            avg_balance = sum(balances) / len(balances) if balances else 0
            
            return {
                'banking_min_balance': min_balance,
                'banking_avg_balance': avg_balance,
                'banking_bounce_count': bounces,
            }
        except:
            return {}
    
    @staticmethod
    def _parse_date(date_str: str) -> Optional[datetime]:
        if not date_str:
            return None
        formats = ['%Y-%m-%d', '%d-%m-%Y', '%d/%m/%Y', '%Y/%m/%d']
        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt)
            except:
                continue
        return None
    
    @staticmethod
    def _calculate_completeness(data: Dict[str, Any]) -> float:
        expected_fields = [
            'gstr1_filing_date', 'gstr1_total_sales',
            'gstr3b_filing_date', 'gstr3b_total_sales',
            'itr_filing_date', 'itr_net_profit',
            'banking_avg_balance'
        ]
        filled = sum(1 for field in expected_fields if data.get(field))
        return (filled / len(expected_fields)) * 100