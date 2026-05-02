# COMPLETE main.py - Copy this entire content to C:\vertibis-backend\app\main.py

"""
Vertibis Backend - Complete with Day 2 Scoring
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.extractors import DataExtractor
from app.scoring_engine import ScoringEngine
from app.advisory_generator import AdvisoryGenerator

# Create FastAPI app
app = FastAPI(
    title="Vertibis API",
    description="MSME Business Health Scoring Platform",
    version="1.0.0"
)

# Add CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Health check
@app.get("/health")
def health_check():
    return {"status": "ok"}

# Sample report with Day 2 scoring
@app.get("/api/v1/ca/sample-report")
def get_sample_report():
    """Returns a sample report with calculated scores"""
    
    # Sample data
    files_dict = {
        'gstr1': '{"filing_date": "2024-04-20", "total_taxable_supplies": 6200000, "total_itc_claimed": 4500000, "amendments_count": 1}',
        'gstr3b': '{"filing_date": "2024-04-22", "total_sales": 6000000, "total_itc_availed": 4200000, "gst_payment": 240000}',
        'gstr2a': '{"supplier_count": 45, "itc_received": 4200000, "discrepancies_count": 1}',
        'itr': '{"filing_date": "2024-07-15", "total_turnover": 5500000, "net_profit": 550000, "profit_margin_pct": 10.0}',
        'banking': 'date,balance,bounce_count\n2024-01-01,500000,0\n2024-01-02,620000,0\n2024-01-03,660000,1\n2024-01-04,710000,0'
    }
    
    # Step 1: Extract data
    extracted_data = DataExtractor.extract_all(files_dict, "2024-25")
    
    # Step 2: Calculate score
    scores = ScoringEngine.calculate_score(extracted_data, "trading", 6200000)
    
    # Step 3: Generate advisory
    advisory = AdvisoryGenerator.generate_advisory(
        extracted_data, scores, "trading", "Test Business"
    )
    
    # Return response
    return {
        "status": "success",
        "report": {
            "health_score": scores['total_score'],
            "score_breakdown": scores['components'],
            "issues": scores['issues'],
            "advisory": advisory,
            "data_completeness_pct": extracted_data.get('data_completeness_pct', 0)
        }
    }

# Root endpoint
@app.get("/")
def root():
    return {
        "message": "Welcome to Vertibis API",
        "docs": "/docs",
        "health": "/health"
    }