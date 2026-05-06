from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from pydantic import BaseModel
from datetime import datetime

from app.database import get_db
from app.models.models import User, AgentConfig, AuditLog
from app.routers.auth import require_superadmin

router = APIRouter()


class AgentConfigUpdate(BaseModel):
    value: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class AgentConfigCreate(BaseModel):
    name: str
    value: str
    description: Optional[str] = None


@router.get("/")
def list_agent_configs(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin)
):
    configs = db.query(AgentConfig).all()
    return [
        {
            "id": c.id,
            "name": c.name,
            "value": c.value,
            "description": c.description,
            "is_active": c.is_active,
            "updated_at": c.updated_at
        } for c in configs
    ]


@router.post("/")
def create_agent_config(
    config_data: AgentConfigCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin)
):
    existing = db.query(AgentConfig).filter(AgentConfig.name == config_data.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Config name already exists")

    config = AgentConfig(
        name=config_data.name,
        value=config_data.value,
        description=config_data.description,
        updated_by=current_user.id
    )
    db.add(config)
    db.commit()
    return {"message": "Config created"}


@router.put("/{config_id}")
def update_agent_config(
    config_id: int,
    config_data: AgentConfigUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin)
):
    config = db.query(AgentConfig).filter(AgentConfig.id == config_id).first()
    if not config:
        raise HTTPException(status_code=404, detail="Config not found")

    old_value = config.value
    update_data = config_data.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(config, key, value)
    config.updated_by = current_user.id
    config.updated_at = datetime.utcnow()

    audit = AuditLog(
        user_id=current_user.id,
        action="UPDATE_AGENT_CONFIG",
        resource_type="agent_config",
        resource_id=str(config_id),
        old_value=old_value,
        new_value=config_data.value,
        status="success"
    )
    db.add(audit)
    db.commit()
    return {"message": "Config updated"}


@router.get("/house-rules")
def get_house_rules(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin)
):
    config = db.query(AgentConfig).filter(AgentConfig.name == "house_rules").first()
    if not config:
        raise HTTPException(status_code=404, detail="House rules not found")
    return {"house_rules": config.value}


@router.put("/house-rules")
def update_house_rules(
    data: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin)
):
    config = db.query(AgentConfig).filter(AgentConfig.name == "house_rules").first()
    if not config:
        raise HTTPException(status_code=404, detail="House rules not found")
    old_val = config.value
    config.value = data.get("house_rules", config.value)
    config.updated_by = current_user.id
    config.updated_at = datetime.utcnow()

    audit = AuditLog(
        user_id=current_user.id,
        action="UPDATE_HOUSE_RULES",
        resource_type="agent_config",
        old_value=old_val[:100] if old_val else None,
        status="success"
    )
    db.add(audit)
    db.commit()
    return {"message": "House rules updated"}


@router.delete("/{config_id}")
def delete_agent_config(
    config_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin)
):
    config = db.query(AgentConfig).filter(AgentConfig.id == config_id).first()
    if not config:
        raise HTTPException(status_code=404, detail="Config not found")
    name = config.name
    db.delete(config)
    audit = AuditLog(
        user_id=current_user.id,
        action="DELETE_AGENT_CONFIG",
        resource_type="agent_config",
        resource_id=str(config_id),
        old_value=name,
        status="success"
    )
    db.add(audit)
    db.commit()
    return {"message": f"Agent config '{name}' deleted"}
