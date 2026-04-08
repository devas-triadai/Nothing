from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models.models import User, AgentConfig
from app.utils.security import get_password_hash
from datetime import datetime


def seed_superadmin():
    db: Session = SessionLocal()
    try:
        existing = db.query(User).filter(User.username == "agra_admin").first()
        if not existing:
            superadmin = User(
                username="agra_admin",
                email="admin@agra.icg.gov.in",
                full_name="AGRA Super Administrator",
                hashed_password=get_password_hash("ICG@AGRA#2026"),
                role="super_admin",
                status="active",
                is_superadmin=True,
                department="ICG HQ - IT Division",
                rank="Super Admin",
                service_number="AGRA-SA-001",
                created_at=datetime.utcnow()
            )
            db.add(superadmin)
            db.commit()
            print("[AGRA] Super Admin seeded successfully.")
        else:
            print("[AGRA] Super Admin already exists.")

        # Seed default agent configs
        default_configs = [
            {"name": "house_rules", "value": "You are AGRA, an AI assistant for the Indian Coast Guard. Always respond professionally and accurately. Do not share classified information.", "description": "System prompt / house rules for the AI agent"},
            {"name": "max_tokens", "value": "2048", "description": "Maximum tokens per response"},
            {"name": "temperature", "value": "0.7", "description": "LLM temperature setting"},
            {"name": "model_name", "value": "local-llm", "description": "Active LLM model name"},
            {"name": "ppt_max_slides", "value": "20", "description": "Maximum slides for PPT generation"},
            {"name": "rag_top_k", "value": "5", "description": "Top-K documents for RAG retrieval"},
        ]

        for config in default_configs:
            existing_config = db.query(AgentConfig).filter(AgentConfig.name == config["name"]).first()
            if not existing_config:
                db.add(AgentConfig(**config))

        db.commit()
        print("[AGRA] Default agent configs seeded.")
    except Exception as e:
        print(f"[AGRA] Seeding error: {e}")
        db.rollback()
    finally:
        db.close()
