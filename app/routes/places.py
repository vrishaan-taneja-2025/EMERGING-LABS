from fastapi import APIRouter, Form, HTTPException, Request, Depends
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.place import Place
from app.core.auth_guard import require_user

templates = Jinja2Templates(directory="app/templates")
router = APIRouter()

# List all places
@router.get("/places")
def list_places(request: Request, user=Depends(require_user), db: Session = Depends(get_db)):
    search = request.query_params.get("search", "")
    page = int(request.query_params.get("page", 1))
    per_page = 10
    query = db.query(Place)
    if search:
        query = query.filter(Place.name.ilike(f"%{search}%"))
    total = query.count()
    places = query.offset((page-1)*per_page).limit(per_page).all()
    return templates.TemplateResponse("places.html", {
        "request": request,
        "user": user,
        "places": places,
        "page": page,
        "per_page": per_page,
        "total": total,
        "search": search
    })

# Add new place page
@router.post("/places/create")
def create_place(name: str = Form(...), description: str = Form(None), db: Session = Depends(get_db)):
    place = Place(name=name, description=description)
    db.add(place)
    db.commit()
    return RedirectResponse("/places/", status_code=302)

# POST API to save new place
@router.post("/places/edit/{place_id}")
def edit_place(
    place_id: int,
    name: str = Form(...),
    description: str = Form(None),  # ✅ added description
    db: Session = Depends(get_db),
    user=Depends(require_user)
):

    place = db.query(Place).filter(Place.id == place_id).first()
    if not place:
        raise HTTPException(status_code=404, detail="Place not found")

    # Update both name and description
    place.name = name
    place.description = description  # ✅ update description
    db.commit()

    return RedirectResponse("/places/", status_code=302)

@router.post("/places/edit/{place_id}")
def edit_place(
    place_id: int,
    name: str = Form(...),
    db: Session = Depends(get_db),
    user=Depends(require_user)
):
    place = db.query(Place).filter(Place.id == place_id).first()
    if not place:
        raise HTTPException(status_code=404, detail="Place not found")
    place.name = name
    db.commit()
    return RedirectResponse("/places", status_code=302)



@router.get("/places/delete/{place_id}")
def delete_place(
    place_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_user)
):
    place = db.query(Place).filter(Place.id == place_id).first()
    if not place:
        raise HTTPException(status_code=404, detail="Place not found")
    db.delete(place)
    db.commit()
    return RedirectResponse("/places", status_code=302)
