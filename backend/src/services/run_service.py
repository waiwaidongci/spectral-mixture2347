import csv,io
import numpy as np
from redis import Redis
from fastapi import HTTPException
from ..models import SpectralLibrary,Endmember,MixtureSample,UnmixRun,ReplicationNote
from ..config.settings import REDIS_URL
from ..utils.serialize import record
from .unmix_algorithm import matrix_diagnostics
from .contamination_service import resolve_groups_for_selection,stale_groups
from .audit_service import log
queue=Redis.from_url(REDIS_URL,decode_responses=True)
def _annotate(db,row):
    data=record(row)
    frozen=(row.input_snapshot or {}).get('contamination_groups') or []
    data['stale_groups']=stale_groups(db,row.library_id,frozen)
    data['uses_contamination']=bool(frozen)
    return data
def list_runs(db):return [_annotate(db,r) for r in db.query(UnmixRun).order_by(UnmixRun.id.desc())]
def get_run(db,rid):
    row=db.get(UnmixRun,rid)
    if not row:raise HTTPException(404,"解混运行不存在")
    return row
def get_run_payload(db,rid):return _annotate(db,get_run(db,rid))

def create_snapshot(db,library,sample_ids,contamination_groups=None):
    members=db.query(Endmember).filter_by(library_id=library.id).order_by(Endmember.code).all()
    samples=db.query(MixtureSample).filter(MixtureSample.id.in_(sample_ids),MixtureSample.library_id==library.id).order_by(MixtureSample.code).all()
    if len(samples)!=len(sample_ids):raise HTTPException(422,"样本重复、不存在或不属于所选光谱库")
    return {"library":record(library),"endmembers":[record(e) for e in members],"samples":[record(s) for s in samples],"contamination_groups":contamination_groups or []}
def create_run(db,data,user):
    library=db.get(SpectralLibrary,data.library_id)
    if not library:raise HTTPException(404,"光谱库不存在")
    if len(set(data.sample_ids))!=len(data.sample_ids) or len(data.sample_ids)*data.repeats>480:raise HTTPException(422,"样本不可重复，样本数×重复数不得超过480")
    selected=db.query(MixtureSample).filter(MixtureSample.id.in_(data.sample_ids),MixtureSample.library_id==library.id).order_by(MixtureSample.code).all()
    if len(selected)!=len(data.sample_ids):raise HTTPException(422,"样本不存在或不属于所选光谱库")
    groups=resolve_groups_for_selection(db,library,selected)
    snapshot=create_snapshot(db,library,data.sample_ids,groups)
    try:
        _,d=matrix_diagnostics(np.array([e['spectrum'] for e in snapshot['endmembers']]).T)
        if not d['supported']:raise ValueError(d['reason'])
    except ValueError as e:raise HTTPException(422,str(e))
    row=UnmixRun(**data.model_dump(),input_snapshot=snapshot,owner=user.name)
    db.add(row);db.flush();log(db,user.email,"unmix.enqueue",row.id);db.commit()
    try:queue.rpush("spectral:jobs",row.id)
    except Exception:
        row.status="failed";row.error="队列不可用，请重提";db.commit();raise HTTPException(503,row.error)
    return _annotate(db,db.get(UnmixRun,row.id))
def rerun_run(db,rid,user):
    """Recompute from the original observations under the current group rules.

    The new run freezes today's registrations; the old run and any approved
    export of it keep the basis they were computed with.
    """
    previous=get_run(db,rid)
    if previous.status not in ("completed","failed"):raise HTTPException(409,"研究尚未完成，不能重算")
    selected=[s for s in db.query(MixtureSample).filter(MixtureSample.id.in_(previous.sample_ids),MixtureSample.library_id==previous.library_id).order_by(MixtureSample.code).all()]
    if len(selected)!=len(previous.sample_ids):raise HTTPException(422,"原研究样本已不存在，无法从原始观测重算")
    groups=resolve_groups_for_selection(db,db.get(SpectralLibrary,previous.library_id),selected)
    snapshot=create_snapshot(db,db.get(SpectralLibrary,previous.library_id),previous.sample_ids,groups)
    row=UnmixRun(name=previous.name+" · 串样重算",library_id=previous.library_id,sample_ids=list(previous.sample_ids),
                 noise_sigma=previous.noise_sigma,repeats=previous.repeats,seed=previous.seed,
                 input_snapshot=snapshot,owner=user.name)
    db.add(row);db.flush();log(db,user.email,"unmix.recompute",row.id);db.commit()
    try:queue.rpush("spectral:jobs",row.id)
    except Exception:
        row.status="failed";row.error="队列不可用，请重提";db.commit();raise HTTPException(503,row.error)
    return _annotate(db,db.get(UnmixRun,row.id))
def export_run(db,rid):
    row=get_run(db,rid)
    if row.status!="completed" or not db.query(ReplicationNote).filter_by(run_id=rid,status="approved").first():raise HTTPException(403,"仅获批完成研究可导出")
    out=io.StringIO();w=csv.writer(out)
    w.writerow(['sample','contamination_group','contamination_version','unique','endmember','weight','feasible_lower','feasible_upper','conditional_q025','conditional_q975','rss','rmse','uniqueness_note','noise_sigma','repeats','root_seed','algorithm_version','input_hash'])
    for s in row.result['samples']:
        fit=s['point_fit'];unique=s.get('unique',True)
        lower=s.get('feasible_lower');upper=s.get('feasible_upper')
        q025=s.get('lower');q975=s.get('upper')
        for i,e in enumerate(row.result['endmembers']):
            w.writerow([s['code'],s.get('group_code') or '',s.get('group_version') or '',unique,e['code'],fit['weights'][i],
                        '' if lower is None else lower[i],'' if upper is None else upper[i],
                        '' if q025 is None else q025[i],'' if q975 is None else q975[i],
                        fit['rss'],fit['rmse'],s.get('interval_note') if unique is False else '',row.noise_sigma,row.repeats,row.seed,row.result.get('algorithm_version',''),row.result['input_hash']])
    return out.getvalue()
