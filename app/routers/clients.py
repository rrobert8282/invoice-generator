from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth import get_current_user
from app import models, schemas

router = APIRouter(prefix="/clients", tags=["clients"])


def get_client_or_404(client_id: str, current_user: models.User, db: Session) -> models.Client:
    # Filtering by user_id here (not just id) is what makes another user's client
    # return 404 instead of 403 -- we don't want to confirm the ID even exists.
    client = (
        db.query(models.Client)
        .filter(models.Client.id == client_id, models.Client.user_id == current_user.id)
        .first()
    )
    if client is None:
        raise HTTPException(status_code=404, detail="Client not found")
    return client


@router.post("", response_model=schemas.ClientOut, status_code=201)
def create_client(
    payload: schemas.ClientCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    client = models.Client(**payload.model_dump(), user_id=current_user.id)
    db.add(client)
    db.commit()
    db.refresh(client)
    return client


@router.get("", response_model=list[schemas.ClientOut])
def list_clients(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return (
        db.query(models.Client)
        .filter(models.Client.user_id == current_user.id)
        .order_by(models.Client.created_at.desc())
        .all()
    )


@router.get("/{client_id}", response_model=schemas.ClientOut)
def get_client(
    client_id: str,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return get_client_or_404(client_id, current_user, db)


@router.patch("/{client_id}", response_model=schemas.ClientOut)
def update_client(
    client_id: str,
    payload: schemas.ClientUpdate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    client = get_client_or_404(client_id, current_user, db)
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(client, field, value)
    db.commit()
    db.refresh(client)
    return client


@router.delete("/{client_id}", status_code=204)
def delete_client(
    client_id: str,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    client = get_client_or_404(client_id, current_user, db)
    db.delete(client)
    db.commit()
