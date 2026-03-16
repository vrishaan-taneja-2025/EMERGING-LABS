from fastapi import APIRouter, Request, Form, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from datetime import date
import datetime

from app.db.session import get_db
from app.core.auth_guard import require_user
from fastapi.templating import Jinja2Templates

from app.models.daily_inspection import DailyInspection
from app.models.di_equipment_log import DIEquipmentLog
from app.models.di_workflow import DIWorkflow
from app.models.equipment import Equipment
from app.models.metadata import EquipmentMetadata

router = APIRouter(prefix="/di", tags=["Daily Inspection"])
templates = Jinja2Templates(directory="app/templates")




@router.get("/")
def di_dashboard(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_user)
):
    recent_di = (
        db.query(DailyInspection)
        .order_by(DailyInspection.created_at.desc())
        .limit(5)
        .all()
    )

    return templates.TemplateResponse(
        "di_dashboard.html",
        {
            "request": request,
            "user": user,
            "recent_di": recent_di
        }
    )

# --------------------------------------------------
# DI FLOW
# --------------------------------------------------
DI_FLOW = {
    "submitted": "supervisor",
    "supervisor_approved": "reviewer",
    "reviewer_approved": "manager",
}

# ==================================================
# USER – CREATE DI FORM
# ==================================================
@router.get("/form")
def di_form(request: Request, db: Session = Depends(get_db), user=Depends(require_user)):
    equipments = db.query(Equipment).join(Equipment.place).order_by(Equipment.place_id).all()

    places = {}
    for eq in equipments:
        pid = eq.place_id or 0
        if pid not in places:
            places[pid] = {
                "name": eq.place.name if eq.place else "Unknown",
                "equipments": []
            }
        places[pid]["equipments"].append(eq)

    return templates.TemplateResponse("di_form.html", {
        "request": request,
        "user": user,
        "places": places
    })

# ==================================================
# USER – SUBMIT DI
# ==================================================
@router.post("/form")
async def submit_di(request: Request, db: Session = Depends(get_db), user=Depends(require_user)):
    form = await request.form()

    di = DailyInspection(
        inspection_date=date.today(),
        created_by=user.id,
        status="submitted"
    )
    db.add(di)
    db.commit()
    db.refresh(di)

    for key, value in form.items():
        if key.startswith("serviceability_"):
            eq_id = int(key.split("_")[1])
            remarks = form.get(f"remarks_{eq_id}", "")
            db.add(DIEquipmentLog(
                di_id=di.id,
                equipment_id=eq_id,
                serviceability=value,
                remarks=remarks
            ))

    db.commit()
    return RedirectResponse("/di/list", 302)

# ==================================================
# LIST DI
# ==================================================
@router.get("/list")
def list_di(request: Request, db: Session = Depends(get_db), user=Depends(require_user)):
    di_list = db.query(DailyInspection).order_by(DailyInspection.created_at.desc()).all()
    return templates.TemplateResponse("di_list.html", {
        "request": request,
        "user": user,
        "di_list": di_list
    })

# ==================================================
# SUPERVISOR – ADD METADATA
# ==================================================
@router.get("/supervisor/{di_id}")
def supervisor_view(di_id: int, request: Request, db: Session = Depends(get_db), user=Depends(require_user)):
    di = db.query(DailyInspection).get(di_id)
    if not di or di.status != "submitted":
        raise HTTPException(403)

    return templates.TemplateResponse("di_supervisor.html", {
        "request": request,
        "di": di,
        "user": user
    })

@router.post("/supervisor/metadata/{equipment_id}")
def add_metadata(
    equipment_id: int,
    pressure: float = Form(None),
    temperature: float = Form(None),
    voltage: float = Form(None),
    frequency: float = Form(None),
    db: Session = Depends(get_db),
    user=Depends(require_user)
):
    if not any([pressure, temperature, voltage, frequency]):
        return RedirectResponse("/di/list", 302)

    db.add(EquipmentMetadata(
        equipment_id=equipment_id,
        pressure=pressure,
        temperature=temperature,
        voltage=voltage,
        frequency=frequency
    ))
    db.commit()
    return RedirectResponse("/di/list", 302)

# ==================================================
# SUPERVISOR APPROVE
# ==================================================
@router.post("/workflow/supervisor/approve/{di_id}")
def supervisor_approve(di_id: int, comments: str = Form(None), db: Session = Depends(get_db), user=Depends(require_user)):
    di = db.query(DailyInspection).get(di_id)
    if di.status != "submitted":
        raise HTTPException(403)

    di.status = "supervisor_approved"
    db.add(DIWorkflow(
        di_id=di.id,
        from_role="supervisor",
        to_role="reviewer",
        action="approved",
        comments=comments,
        acted_by=user.id
    ))
    db.commit()
    return RedirectResponse("/di/list", 302)

# ==================================================
# REVIEWER APPROVE
# ==================================================
@router.post("/workflow/reviewer/approve/{di_id}")
def reviewer_approve(di_id: int, comments: str = Form(None), db: Session = Depends(get_db), user=Depends(require_user)):
    di = db.query(DailyInspection).get(di_id)
    if di.status != "supervisor_approved":
        raise HTTPException(403)

    di.status = "reviewer_approved"
    db.add(DIWorkflow(
        di_id=di.id,
        from_role="reviewer",
        to_role="manager",
        action="approved",
        comments=comments,
        acted_by=user.id
    ))
    db.commit()
    return RedirectResponse("/di/list", 302)

# ==================================================
# MANAGER FINAL APPROVE
# ==================================================
@router.post("/workflow/manager/approve/{di_id}")
def manager_approve(di_id: int, comments: str = Form(None), db: Session = Depends(get_db), user=Depends(require_user)):
    di = db.query(DailyInspection).get(di_id)
    if di.status != "reviewer_approved":
        raise HTTPException(403)

    di.status = "completed"
    db.add(DIWorkflow(
        di_id=di.id,
        from_role="manager",
        to_role="completed",
        action="approved",
        comments=comments,
        acted_by=user.id
    ))
    db.commit()
    return RedirectResponse("/di/list", 302)




@router.post("/workflow/approve/{di_id}")
def supervisor_approve(
    di_id: int,
    comments: str = Form(None),
    db: Session = Depends(get_db),
    user=Depends(require_user)
):
    di = db.query(DailyInspection).filter_by(id=di_id).first()
    if not di:
        raise HTTPException(404, "DI not found")

    if di.status != "submitted":
        raise HTTPException(403, "Invalid DI state")

    if user.role.name != "supervisor":
        raise HTTPException(403, "Only supervisor can approve")

    di.status = "supervisor_approved"

    wf = DIWorkflow(
        di_id=di.id,
        from_role="supervisor",
        to_role="reviewer",
        action="approved",
        comments=comments,
        acted_by=user.id
    )

    db.add(wf)
    db.commit()

    return RedirectResponse("/di/list", status_code=302)








@router.post("/workflow/reviewer/approve/{di_id}")
def reviewer_approve(
    di_id: int,
    comments: str = Form(None),
    db: Session = Depends(get_db),
    user=Depends(require_user)
):
    di = db.query(DailyInspection).filter_by(id=di_id).first()
    if not di:
        raise HTTPException(404)

    if di.status != "supervisor_approved":
        raise HTTPException(403)

    if user.role.name != "reviewer":
        raise HTTPException(403)

    di.status = "reviewer_approved"

    wf = DIWorkflow(
        di_id=di.id,
        from_role="reviewer",
        to_role="manager",
        action="approved",
        comments=comments,
        acted_by=user.id
    )

    db.add(wf)
    db.commit()

    return RedirectResponse("/di/list", status_code=302)





@router.post("/workflow/manager/approve/{di_id}")
def manager_approve(
    di_id: int,
    comments: str = Form(None),
    db: Session = Depends(get_db),
    user=Depends(require_user)
):
    di = db.query(DailyInspection).filter_by(id=di_id).first()
    if not di:
        raise HTTPException(404)

    if di.status != "reviewer_approved":
        raise HTTPException(403)

    if user.role.name != "manager":
        raise HTTPException(403)

    di.status = "completed"

    wf = DIWorkflow(
        di_id=di.id,
        from_role="manager",
        to_role="completed",
        action="approved",
        comments=comments,
        acted_by=user.id
    )

    db.add(wf)
    db.commit()

    return RedirectResponse("/di/list", status_code=302)




@router.post("/workflow/reject/{di_id}")
def reject_di(
    di_id: int,
    comments: str = Form(...),
    db: Session = Depends(get_db),
    user=Depends(require_user)
):
    di = db.query(DailyInspection).filter_by(id=di_id).first()
    if not di:
        raise HTTPException(404)

    di.status = "rejected"

    wf = DIWorkflow(
        di_id=di.id,
        from_role=user.role.name,
        to_role="creator",
        action="rejected",
        comments=comments,
        acted_by=user.id
    )

    db.add(wf)
    db.commit()

    return RedirectResponse("/di/list", status_code=302)




