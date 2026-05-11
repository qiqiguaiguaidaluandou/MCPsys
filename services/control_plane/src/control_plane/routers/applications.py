from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from mcpsys_shared.models import Application, User

from ..audit import Action, audit_log, model_to_dict
from ..deps import get_db, require_role

router = APIRouter(prefix="/api/v1/applications", tags=["applications"])


class ApplicationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    team: str | None = None
    description: str | None = None


class ApplicationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    owner_user_id: int
    team: str | None
    description: str | None


class ApplicationList(BaseModel):
    items: list[ApplicationOut]
    total: int


@router.post(
    "",
    response_model=ApplicationOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_application(
    payload: ApplicationCreate,
    request: Request,
    current_user: User = Depends(require_role("admin", "operator")),
    db: AsyncSession = Depends(get_db),
) -> ApplicationOut:
    app_obj = Application(
        name=payload.name,
        team=payload.team,
        description=payload.description,
        owner_user_id=current_user.id,
    )
    db.add(app_obj)
    try:
        await db.flush()
    except IntegrityError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, "name already exists") from e
    await audit_log(
        db,
        action=Action.APPLICATION_CREATE,
        target_type="application",
        target_id=str(app_obj.id),
        before=None,
        after=model_to_dict(app_obj),
        actor=current_user,
        request=request,
    )
    return ApplicationOut.model_validate(app_obj)


@router.get(
    "",
    response_model=ApplicationList,
    dependencies=[Depends(require_role("admin", "operator", "viewer"))],
)
async def list_applications(db: AsyncSession = Depends(get_db)) -> ApplicationList:
    res = await db.execute(select(Application).order_by(Application.id))
    items = res.scalars().all()
    return ApplicationList(
        items=[ApplicationOut.model_validate(a) for a in items], total=len(items)
    )
