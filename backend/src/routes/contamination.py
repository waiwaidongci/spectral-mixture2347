from fastapi import APIRouter,Depends
from sqlalchemy.orm import Session
from ..config.database import get_db
from ..controllers.dependencies import current_user,roles
from ..constants.roles import Role
from ..schemas.contamination import GroupInput,RegistrationInput
from ..services.contamination_service import list_groups,create_group,add_registration
router=APIRouter(tags=["contamination"])
@router.get("/libraries/{lid}/contamination-groups")
def index(lid:int,db:Session=Depends(get_db),user=Depends(current_user)):return list_groups(db,lid)
@router.post("/libraries/{lid}/contamination-groups",status_code=201)
def create(lid:int,data:GroupInput,db:Session=Depends(get_db),user=Depends(roles(Role.ADMIN,Role.ANALYST))):return create_group(db,lid,data,user)
@router.post("/contamination-groups/{gid}/registrations",status_code=201)
def register(gid:int,data:RegistrationInput,db:Session=Depends(get_db),user=Depends(roles(Role.ADMIN,Role.ANALYST))):return add_registration(db,gid,data,user)
