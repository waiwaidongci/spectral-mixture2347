from sqlalchemy import String,Text,JSON,ForeignKey,Integer,UniqueConstraint
from sqlalchemy.orm import Mapped,mapped_column
from ..config.database import Base
from ..utils.clock import now

class ContaminationGroup(Base):
    __tablename__="contamination_groups"
    __table_args__=(UniqueConstraint("library_id","code"),)
    id:Mapped[int]=mapped_column(primary_key=True)
    library_id:Mapped[int]=mapped_column(ForeignKey("spectral_libraries.id"))
    code:Mapped[str]=mapped_column(String(40))
    name:Mapped[str]=mapped_column(String(120))
    note:Mapped[str]=mapped_column(Text,default="")
    created_by:Mapped[str]=mapped_column(String(100))
    created_at:Mapped[str]=mapped_column(String(64),default=now)

class ContaminationRegistration(Base):
    __tablename__="contamination_registrations"
    __table_args__=(UniqueConstraint("group_id","version"),)
    id:Mapped[int]=mapped_column(primary_key=True)
    group_id:Mapped[int]=mapped_column(ForeignKey("contamination_groups.id"))
    version:Mapped[int]=mapped_column(Integer)
    member_sample_ids:Mapped[list]=mapped_column(JSON)
    matrix:Mapped[list]=mapped_column(JSON)
    note:Mapped[str]=mapped_column(Text,default="")
    created_by:Mapped[str]=mapped_column(String(100))
    created_at:Mapped[str]=mapped_column(String(64),default=now)
