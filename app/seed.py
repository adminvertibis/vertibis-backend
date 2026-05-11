"""
Quick seed for 10-day testing.
Run from project root: python -m app.seed
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.database import SessionLocal, create_tables
from app.models import Partner, Client


def seed():
    create_tables()
    db = SessionLocal()
    try:
        if db.query(Partner).first():
            print("Database already has data — skipping seed.")
            return

        partner = Partner(
            name="Sushant CA Firm",
            email="sushant@vertibis.in",
            phone="9876543210",
            firm_type="CA",
            gstin="27ABCDE1234F1Z5",
            credits_balance=500,
            status="active",
        )
        db.add(partner)
        db.flush()

        clients_data = [
            dict(name="Ravi Textiles", business_name="Ravi Textiles Pvt Ltd",
                 gstin="27AAACR1234D1ZV", industry="trading", turnover=6200000),
            dict(name="Priya Manufacturing", business_name="Priya Mfg Works",
                 gstin="27BBBCP5678E1Z3", industry="manufacturing", turnover=12000000),
            dict(name="TechServ Solutions", business_name="TechServ Solutions LLP",
                 gstin="27CCCCT9012F1Z1", industry="it", turnover=8000000),
        ]

        client_objs = []
        for cd in clients_data:
            c = Client(partner_id=partner.id, **cd)
            db.add(c)
            client_objs.append(c)

        db.commit()
        for c in client_objs:
            db.refresh(c)

        print(f"Seeded: 1 partner + {len(clients_data)} clients")
        print(f"Partner ID: {partner.id}")
        for c in client_objs:
            print(f"  Client: {c.name}  ->  {c.id}")

    finally:
        db.close()


if __name__ == "__main__":
    seed()
