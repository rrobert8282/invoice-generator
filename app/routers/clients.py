from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas

router = APIRouter(prefix="/clients", tags=["clients"])


def get_client_or_404(client_id: str, db: Session) -> models.Client:
    client = db.query(models.Client).filter(models.Client.id == client_id).first()
    if client is None:
        raise HTTPException(status_code=404, detail="Client not found")
    return client


@router.post("", response_model=schemas.ClientOut, status_code=201)
def create_client(payload: schemas.ClientCreate, db: Session = Depends(get_db)):
    client = models.Client(**payload.model_dump())
    db.add(client)
    db.commit()
    db.refresh(client)
    return client


@router.get("", response_model=list[schemas.ClientOut])
def list_clients(db: Session = Depends(get_db)):
    return db.query(models.Client).order_by(models.Client.created_at.desc()).all()


@router.get("/{client_id}", response_model=schemas.ClientOut)
def get_client(client_id: str, db: Session = Depends(get_db)):
    return get_client_or_404(client_id, db)


@router.patch("/{client_id}", response_model=schemas.ClientOut)
def update_client(client_id: str, payload: schemas.ClientUpdate, db: Session = Depends(get_db)):
    client = get_client_or_404(client_id, db)
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(client, field, value)
    db.commit()
    db.refresh(client)
    return client


@router.delete("/{client_id}", status_code=204)
def delete_client(client_id: str, db: Session = Depends(get_db)):
    client = get_client_or_404(client_id, db)
    db.delete(client)
    db.commit()
