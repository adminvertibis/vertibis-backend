"""
DAY 2 PART 4: API ROUTES & INTEGRATION
File: app/day2_routes.py

Endpoint for processing uploads: Extract → Score → Generate Advisory
"""

from fastapi import APIRouter, Form, UploadFile, File, HTTPException
from typing import Optional
import uuid

# Import the classes you created
# from app.extractors import DataExtractor
# from app.scoring_engine import ScoringEngine, Industry, TurnoverSize
# from app.advisory_generator import AdvisoryGenerator

router = APIRouter()

@router.post("/api/v1/ca/process-upload")
async def process_upload(
    client_id: str = Form(...),
    client_name: str = Form(...),
    client_gstin: str = Form(...),
    industry: str = Form(...),  # "manufacturing", "trading", "services", "it"
    turnover: float = Form(...),  # Annual turnover in rupees
    fy_year: str = Form(...),
    gstr1: Optional[UploadFile] = File(None),
    gstr3b: Optional[UploadFile] = File(None),
    gstr2a: Optional[UploadFile] = File(None),
    itr: Optional[UploadFile] = File(None),
    banking: Optional[UploadFile] = File(None),
):
    """
    Process uploaded files: Extract → Score → Generate Advisory
    
    This is the Day 2 main endpoint.
    
    Request:
    - POST /api/v1/ca/process-upload
    - multipart/form-data with 5 files + client info
    
    Response:
    - Health score (0-100)
    - Score breakdown (4 components)
    - Issues identified
    - AI-generated advisory
    """
    
    try:
        # Step 1: Read files from upload
        files_dict = {}
        
        if gstr1:
            files_dict['gstr1'] = (await gstr1.read()).decode('utf-8')
        if gstr3b:
            files_dict['gstr3b'] = (await gstr3b.read()).decode('utf-8')
        if gstr2a:
            files_dict['gstr2a'] = (await gstr2a.read()).decode('utf-8')
        if itr:
            files_dict['itr'] = (await itr.read()).decode('utf-8')
        if banking:
            files_dict['banking'] = (await banking.read()).decode('utf-8')
        
        # Step 2: Extract data from files
        # extracted_data = DataExtractor.extract_all(files_dict, fy_year)
        
        # Step 3: Determine industry and size
        # industry_enum = Industry(industry.lower())
        # if turnover < 5000000:  # <50L
        #     size_enum = TurnoverSize.SMALL
        # elif turnover < 500000000:  # <5Cr
        #     size_enum = TurnoverSize.MEDIUM
        # else:
        #     size_enum = TurnoverSize.LARGE
        
        # Step 4: Calculate score
        # scores = ScoringEngine.calculate_score(
        #     extracted_data, industry_enum, size_enum
        # )
        
        # Step 5: Generate advisory
        # advisory_gen = AdvisoryGenerator()
        # advisory = advisory_gen.generate_advisory(
        #     extracted_data, scores, industry, client_name, client_gstin
        # )
        
        # Step 6: Return result
        return {
            "status": "success",
            "client": {
                "name": client_name,
                "gstin": client_gstin,
                "industry": industry,
                "turnover": turnover
            },
            "report": {
                "health_score": 72,  # Replace with scores['total_score']
                "score_breakdown": {
                    "gst_itc_match": 20,
                    "filing_timeliness": 20,
                    "cashflow_health": 18,
                    "data_completeness": 14
                },
                "issues": [
                    "GST-ITR gap ₹7L (11.3%)",
                    "GSTR-3B filed 2 days late",
                    "Low bank balance: ₹2.5L (need ₹3.8L)"
                ],
                "advisory": "Your business is generally healthy (Score: 72/100). Monitor these items...",
                "extracted_data": {
                    "gstr3b_sales": 6000000,
                    "itr_turnover": 5500000,
                    "net_profit": 550000,
                    "bank_balance": 250000,
                },
                "data_completeness_pct": 87.5
            }
        }
    
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/api/v1/ca/sample-report")
async def get_sample_report():
    """
    Get a sample report to show what Day 2 output looks like.
    Use this to test before uploading real files.
    """
    return {
        "status": "success",
        "report": {
            "health_score": 72,
            "score_breakdown": {
                "gst_itc_match": 20,  # Out of 25
                "filing_timeliness": 20,  # Out of 25
                "cashflow_health": 18,  # Out of 25
                "data_completeness": 14  # Out of 25
            },
            "issues": [
                "GST-ITR gap ₹7L (11.3%)",
                "GSTR-3B filed 2 days late",
                "Low bank balance: ₹2.5L (need ₹3.8L)"
            ],
            "advisory": """Your business is generally healthy (Score: 72/100).

You have a GST-ITR gap of ₹7L which indicates some unreconciled income. This creates a 35% notice risk and potential tax exposure of ₹2.1L plus ₹3.15L in penalties.

**Key Issues:**
1. GST-ITR mismatch: ₹7L gap could lead to notice
2. Low bank balance: You have ₹2.5L but need ₹3.8L for safety
3. Late GSTR-3B filing: Reduce penalties by filing on time

**Actions to take:**
1. Reconcile your GST and ITR records by Oct 20, 2025
2. Increase bank balance by ₹1.3L from operating cash
3. Review professional expenses claimed in ITR

**If you fix these issues, you can save ₹3.15L in taxes and penalties and improve your loan eligibility by ₹5L.**""",
            "lending_eligible": 2500000,
            "extracted_data": {
                "gstr3b_sales": 6000000,
                "itr_turnover": 5500000,
                "net_profit": 550000,
                "bank_balance": 250000,
                "gst_itc_gap": 700000,
            },
            "data_completeness_pct": 87.5
        }
    }


# HOW TO INTEGRATE INTO main.py:
# 
# from app.day2_routes import router as day2_router
# app.include_router(day2_router)
#
# Then you can POST to: /api/v1/ca/process-upload
