from database import get_db_connection, get_db_cursor
from uuid import uuid4
from datetime import datetime

def seed_sample_data():
    """Load 10 sample MSMEs for testing"""
    
    with get_db_connection() as conn:
        with get_db_cursor(conn) as cursor:
            # Create sample CA
            ca_id = uuid4()
            ca_user_id = uuid4()
            
            cursor.execute(
                """INSERT INTO users (id, email, name, phone, user_type)
                   VALUES (%s, %s, %s, %s, %s)""",
                (ca_user_id, "testca@example.com", "Test CA", "9999999999", "CA")
            )
            
            cursor.execute(
                """INSERT INTO cas (id, firm_name, icai_membership, client_count)
                   VALUES (%s, %s, %s, %s)""",
                (ca_id, "Test CA Firm", "A12345", 10)
            )
            
            # Create 10 sample clients
            for i in range(10):
                client_id = uuid4()
                gstin = f"27AABCT{1234+i:04d}H1Z0"
                
                cursor.execute(
                    """INSERT INTO clients 
                       (id, ca_id, client_name, gstin, industry, annual_turnover, consent_given, consent_date)
                       VALUES (%s, %s, %s, %s, %s, %s, TRUE, CURRENT_TIMESTAMP)""",
                    (
                        client_id,
                        ca_id,
                        f"ABC Manufacturing {i+1}",
                        gstin,
                        "Manufacturing",
                        6000000,
                    )
                )
            
            print(f"✅ Sample data loaded: 1 CA + 10 clients")

if __name__ == "__main__":
    seed_sample_data()
