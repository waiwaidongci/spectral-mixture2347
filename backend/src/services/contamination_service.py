import numpy as np
from fastapi import HTTPException
from ..models import SpectralLibrary,MixtureSample,ContaminationGroup,ContaminationRegistration
from ..utils.serialize import record
from .audit_service import log

def _validate_members(db,library,ids):
    if len(ids)<2 or len(ids)>6:raise ValueError("串样组须包含2–6份同库样本")
    if len(set(ids))!=len(ids):raise ValueError("串样组成员不可重复")
    rows=db.query(MixtureSample).filter(MixtureSample.id.in_(ids),MixtureSample.library_id==library.id).all()
    by_id={r.id:r for r in rows}
    if len(by_id)!=len(ids):raise ValueError("串样组成员不存在或不属于所选光谱库")
    return [by_id[i] for i in ids]

def _validate_matrix(matrix,size):
    try:C=np.asarray(matrix,dtype=float)
    except (TypeError,ValueError,OverflowError):raise ValueError("串样比例矩阵必须为有限数字")
    if C.shape!=(size,size):raise ValueError(f"串样比例矩阵须为{size}×{size}，行列顺序与成员一致")
    if not np.isfinite(C).all():raise ValueError("串样比例矩阵包含非有限数值")
    if np.any(C<0):raise ValueError("串样比例不得为负")
    totals=C.sum(axis=1)
    if np.any(np.abs(totals-1)>1e-6):raise ValueError("每一份测量中来自各原样本的比例之和须为1")
    return (C/totals[:,None]).tolist()

def _registration_payload(db,registration):
    data=record(registration)
    codes={s.id:s.code for s in db.query(MixtureSample).filter(MixtureSample.id.in_(data['member_sample_ids'])).all()} if data['member_sample_ids'] else {}
    data['member_codes']=[codes.get(i,"#"+str(i)) for i in data['member_sample_ids']]
    return data

def _group_payload(db,group):
    registrations=db.query(ContaminationRegistration).filter_by(group_id=group.id).order_by(ContaminationRegistration.version).all()
    current=_registration_payload(db,registrations[-1]) if registrations else None
    diagnostics=None
    if current:
        singular=np.linalg.svd(np.asarray(current['matrix'],dtype=float),compute_uv=False)
        threshold=max(len(singular),1)*np.finfo(float).eps*singular[0] if singular[0]>0 else 0.
        rank=int(np.sum(singular>threshold))
        diagnostics={"rank":rank,"nullity":len(singular)-rank,"condition_number":float(singular[0]/singular[-1]) if singular[-1]>0 else None}
    return dict(record(group),current=current,version_count=len(registrations),diagnostics=diagnostics)

def list_groups(db,library_id):
    if not db.get(SpectralLibrary,library_id):raise HTTPException(404,"光谱库不存在")
    return [_group_payload(db,g) for g in db.query(ContaminationGroup).filter_by(library_id=library_id).order_by(ContaminationGroup.code)]

def _latest_registration(db,group_id):
    return db.query(ContaminationRegistration).filter_by(group_id=group_id).order_by(ContaminationRegistration.version.desc()).first()

def _ensure_disjoint(db,library_id,group_id,member_ids):
    for other in db.query(ContaminationGroup).filter_by(library_id=library_id).all():
        if other.id==group_id:continue
        latest=_latest_registration(db,other.id)
        if not latest:continue
        overlap=set(member_ids)&set(latest.member_sample_ids)
        if overlap:raise ValueError(f"成员与串样组 {other.code} 重叠；同一份测量只能归入一个组")

def create_group(db,library_id,data,user):
    library=db.get(SpectralLibrary,library_id)
    if not library:raise HTTPException(404,"光谱库不存在")
    if db.query(ContaminationGroup).filter_by(library_id=library_id,code=data.code).first():raise HTTPException(409,"该光谱库已有同编号串样组；请登记新版本")
    try:
        members=_validate_members(db,library,data.member_sample_ids)
        matrix=_validate_matrix(data.matrix,len(members))
        _ensure_disjoint(db,library_id,None,[m.id for m in members])
    except ValueError as e:raise HTTPException(422,str(e))
    group=ContaminationGroup(library_id=library_id,code=data.code,name=data.name,note=data.note,created_by=user.name)
    db.add(group);db.flush()
    registration=ContaminationRegistration(group_id=group.id,version=1,member_sample_ids=[m.id for m in members],matrix=matrix,note=data.registration_note,created_by=user.name)
    db.add(registration);db.flush()
    log(db,user.email,"contamination.register",f"{group.code} v1");db.commit()
    return _group_payload(db,group)

def add_registration(db,group_id,data,user):
    group=db.get(ContaminationGroup,group_id)
    if not group:raise HTTPException(404,"串样组不存在")
    library=db.get(SpectralLibrary,group.library_id)
    try:
        members=_validate_members(db,library,data.member_sample_ids)
        matrix=_validate_matrix(data.matrix,len(members))
        _ensure_disjoint(db,group.library_id,group.id,[m.id for m in members])
    except ValueError as e:raise HTTPException(422,str(e))
    latest=_latest_registration(db,group.id)
    version=(latest.version if latest else 0)+1
    registration=ContaminationRegistration(group_id=group.id,version=version,member_sample_ids=[m.id for m in members],matrix=matrix,note=data.note,created_by=user.name)
    db.add(registration);db.flush()
    log(db,user.email,"contamination.register",f"{group.code} v{version}");db.commit()
    return _group_payload(db,group)

def resolve_groups_for_selection(db,library,selected_samples):
    """Apply every registered group touched by the selection, at its latest version.

    A grouped measurement is never unmixed alone: selecting one member requires
    the whole group.  Ungrouped samples keep the ordinary single-sample path.
    """
    selected={s.id for s in selected_samples};frozen=[];covered=set()
    groups=db.query(ContaminationGroup).filter_by(library_id=library.id).order_by(ContaminationGroup.code).all()
    for group in groups:
        registration=_latest_registration(db,group.id)
        if not registration:continue
        members=list(registration.member_sample_ids)
        touched=selected & set(members)
        if not touched:continue
        missing=set(members)-selected
        if missing:
            codes=[s.code for s in db.query(MixtureSample).filter(MixtureSample.id.in_(missing)).all()]
            raise HTTPException(422,f"串样组 {group.code} 的成员 {', '.join(sorted(codes))} 未纳入；串样样本须整组联合解混")
        overlap=covered & set(members)
        if overlap:raise HTTPException(422,"同一份测量同时属于多个串样组，无法确定联合模型")
        covered|=set(members)
        frozen.append({"group_id":group.id,"code":group.code,"name":group.name,"group_note":group.note,
                       "registration_id":registration.id,"version":registration.version,
                       "member_sample_ids":members,"matrix":registration.matrix,
                       "registration_note":registration.note,"created_by":registration.created_by,
                       "created_at":registration.created_at})
    frozen.sort(key=lambda g:g['code'])
    return frozen

def stale_groups(db,library_id,frozen_groups):
    """Compare a run's frozen registrations with the library's current ones."""
    stale=[]
    for frozen in frozen_groups or []:
        group=db.get(ContaminationGroup,frozen.get('group_id'))
        if not group or group.library_id!=library_id:
            stale.append({"group_id":frozen.get('group_id'),"code":frozen.get('code',''),"frozen_version":frozen.get('version'),"current_version":None,"reason":"串样组已不存在"})
            continue
        latest=_latest_registration(db,group.id)
        current=latest.version if latest else None
        if current!=frozen.get('version'):
            stale.append({"group_id":group.id,"code":group.code,"frozen_version":frozen.get('version'),"current_version":current,"reason":"串样登记已更新"})
    return stale
