"""Regression checks for the joint contamination solver.

Run from backend/:  python -m scripts.check_contamination

These are numerical invariants, not material claims:
  * joint QP optimum equals exhaustive support enumeration on small problems;
  * a non-singular register yields a unique recipe and bounds collapse to it;
  * a singular register yields feasible bounds and no unique recipe;
  * split/cycle/stale-frozen bookkeeping round-trips through the service layer.
"""
import itertools
import numpy as np
from src.services.joint_algorithm import JointModel,joint_feasible_bounds

def _brute_force(A,Y,C):
    m=A.shape[1];n=C.shape[0];best=None
    supports=[s for k in range(1,m+1) for s in itertools.combinations(range(m),k)]
    for chosen in itertools.product(supports,repeat=n):
        base=np.zeros((n,m));free=[]
        for i,sup in enumerate(chosen):
            base[i,list(sup)]=1/len(sup)
            if len(sup)>1:
                _,_,vh=np.linalg.svd(np.ones((1,len(sup))),full_matrices=True)
                free.append((i,list(sup),vh[1:].T))
        columns=[np.outer(C[:,i],(A[:,s]@B)[:,k]).reshape(-1) for i,s,B in free for k in range(B.shape[1])]
        rhs=(C@base@A.T-Y).reshape(-1)
        coef=np.linalg.lstsq(np.column_stack(columns),-rhs,rcond=None)[0] if columns else np.zeros(0)
        weights=base.copy();q=0
        for i,s,B in free:
            for k in range(B.shape[1]):weights[i,s]+=coef[q]*B[:,k];q+=1
        if weights.min()< -1e-9:continue
        weights=np.maximum(weights,0);weights/=weights.sum(axis=1,keepdims=True)
        rss=float(np.sum((C@weights@A.T-Y)**2))
        if best is None or rss<best[0]:best=(rss,weights)
    return best

def check_against_enumeration(trials=60,seed=17):
    rng=np.random.default_rng(seed)
    for trial in range(trials):
        n=int(rng.integers(2,4));m=int(rng.integers(2,5));p=int(rng.integers(m+1,9))
        A=rng.normal(size=(p,m));A[:,0]+=2
        W=rng.dirichlet(np.ones(m)*1.5,size=n)
        C=rng.random((n,n))
        if trial%3==0 and n>2:C[2]=(C[0]+C[1])/2
        C=np.maximum(C,0);C/=C.sum(axis=1,keepdims=True)
        Y=C@W@A.T+rng.normal(0,.01,(n,p))
        model=JointModel(A,C);fit=model.fit(Y)
        brute=_brute_force(A,Y,C)
        if abs(fit['rss']-brute[0])>1e-6*(1+brute[0]):
            raise AssertionError(f"trial {trial}: joint RSS {fit['rss']} != enumeration {brute[0]}")
        bounds=joint_feasible_bounds(model,fit['weights'])
        if np.any(fit['weights']<bounds['lower']-1e-7) or np.any(fit['weights']>bounds['upper']+1e-7):
            raise AssertionError(f"trial {trial}: optimum outside its own feasible bounds")
    print(f"enumeration agreement: {trials} random joint problems OK")

def _base():
    A=np.array([[.2,.35,.7,.15],[.3,.45,.75,.2],[.4,.55,.8,.25],[.5,.6,.85,.3],
                [.6,.55,.9,.35],[.7,.5,.95,.4],[.8,.45,.98,.45],[.9,.4,1.,.5]])
    W=np.array([[.5,.2,.2,.1],[.1,.6,.2,.1],[.2,.1,.3,.4]])
    return A,W

def check_unique_and_degenerate():
    A,W=_base()
    cyclic=np.array([[.94,0,.06],[.05,.93,.02],[0,.07,.93]])
    model=JointModel(A,cyclic);fit=model.fit(cyclic@W@A.T);bounds=joint_feasible_bounds(model,fit['weights'])
    if not bounds['unique']:raise AssertionError("full-rank cyclic register should be jointly identifiable")
    if bounds['max_width']>1e-7:raise AssertionError("unique bounds must collapse")
    if np.max(np.abs(fit['weights']-W))>1e-8:raise AssertionError("cyclic recipes not recovered")
    degenerate=np.array([[.5,.5,0],[.5,.5,0],[0,0,1.]])
    model=JointModel(A,degenerate);fit=model.fit(degenerate@W@A.T);bounds=joint_feasible_bounds(model,fit['weights'])
    if bounds['unique']:raise AssertionError("rank-deficient pooled register must not claim a unique recipe")
    if bounds['nullity']!=1:raise AssertionError("expected one-dimensional joint null space")
    if bounds['max_width']<1e-3:raise AssertionError("degenerate bounds should stay informative, not collapse")
    if np.max(np.abs(bounds['upper'][2]-bounds['lower'][2]))>1e-7:
        raise AssertionError("independent third sample must pin its own recipe")
    if np.max(np.abs(bounds['lower'][2]-W[2]))>1e-7:raise AssertionError("pinned third recipe moved")
    print("unique/degenerate checks OK")

def check_permutation_and_fingerprint():
    from src.services.analysis_service import analyze_unmix
    A,W=_base();C=np.array([[.9,.1,0],[.1,.8,.1],[0,.2,.8]]);Y=C@W@A.T
    def snapshot(order):
        return {"library":{"code":"LS-T","name":"t","description":"","wavelengths":list(range(1,A.shape[0]+1)),"source":"test"},
                "endmembers":[{"id":i+1,"code":f"EM-{i+1}","name":"e","spectrum":A[:,i].tolist()} for i in range(A.shape[1])],
                "samples":[{"id":i+1,"code":f"LS-T-00{i+1}","name":"s","observed":Y[i].tolist(),"note":""} for i in order],
                "contamination_groups":[{"group_id":1,"code":"CG-T","name":"g","group_note":"","registration_id":1,"version":1,
                    "member_sample_ids":[i+1 for i in order],"matrix":C[np.ix_(order,order)].tolist(),
                    "registration_note":"","created_by":"t","created_at":"t"}]}
    forward=analyze_unmix(snapshot([0,1,2]),0,20,2026)
    backward=analyze_unmix(snapshot([2,1,0]),0,20,2026)
    if forward['input_hash']!=backward['input_hash']:
        raise AssertionError("row/column order must not change the frozen joint basis")
    for a,b in zip(forward['samples'],backward['samples']):
        if a['code']!=b['code'] or np.max(np.abs(np.array(a['point_fit']['weights'])-np.array(b['point_fit']['weights'])))>1e-12:
            raise AssertionError("permuted group gave a different recipe")
    print("permutation-invariant fingerprint OK")

def check_group_rules():
    import os,tempfile
    os.environ.setdefault("DATABASE_URL","sqlite:///"+tempfile.mktemp(suffix=".db"))
    from src.config.database import Base,engine,SessionLocal
    from src.models import SpectralLibrary,Endmember,MixtureSample,ContaminationGroup,ContaminationRegistration
    from src.services.contamination_service import resolve_groups_for_selection,create_group,add_registration,stale_groups
    from src.services.run_service import create_snapshot,rerun_run
    Base.metadata.create_all(engine)
    rng=np.random.default_rng(5)
    with SessionLocal() as db:
        lib=SpectralLibrary(code="LS-T",name="t",description="",wavelengths=list(range(1,9)),source="test");db.add(lib);db.flush()
        for j in range(4):db.add(Endmember(library_id=lib.id,code=f"EM-{j+1}",name="e",spectrum=rng.random(8).tolist()))
        samples=[]
        for i in range(4):
            row=MixtureSample(code=f"LS-T-00{i+1}",library_id=lib.id,name="s",observed=rng.random(8).tolist(),note="");db.add(row);samples.append(row)
        db.flush()
        from src.schemas.contamination import GroupInput
        class U:name="tester";email="t@x"
        group=create_group(db,lib.id,GroupInput(code="CG-T",name="group",member_sample_ids=[samples[0].id,samples[1].id],
            matrix=[[.9,.1],[.2,.8]],registration_note="first registration"),U())
        try:resolve_groups_for_selection(db,lib,[samples[0]])
        except Exception as e:
            if getattr(e,"status_code",None)!=422:raise
        else:raise AssertionError("partial group selection must be rejected")
        frozen=resolve_groups_for_selection(db,lib,[samples[0],samples[1],samples[2]])
        if len(frozen)!=1 or frozen[0]['version']!=1:raise AssertionError("frozen registration mismatch")
        snap=create_snapshot(db,lib,[samples[0].id,samples[1].id,samples[2].id],frozen)
        if snap['contamination_groups'][0]['version']!=1:raise AssertionError("snapshot did not freeze version")
        from src.models import UnmixRun
        run=UnmixRun(name="r",library_id=lib.id,sample_ids=[samples[0].id,samples[1].id,samples[2].id],noise_sigma=0,repeats=20,seed=1,
                     input_snapshot=snap,status="completed",result={"samples":[],"endmembers":[],"input_hash":"x"},owner="t")
        db.add(run);db.commit()
        group=add_registration(db,group['id'],type("R",(),{"member_sample_ids":[samples[0].id,samples[1].id],
            "matrix":[[.8,.2],[.1,.9]],"note":"revised after re-weighing"})(),U())
        if group['current']['version']!=2:raise AssertionError("registration version did not advance")
        stale=stale_groups(db,lib.id,snap['contamination_groups'])
        if not stale or stale[0]['frozen_version']!=1 or stale[0]['current_version']!=2:
            raise AssertionError("old run must be flagged against the new registration")
        if db.get(UnmixRun,run.id).result['samples']!=[]:raise AssertionError("old run basis was rewritten")
        try:rerun_run(db,run.id,U())
        except Exception as e:
            if "队列不可用" not in str(e) and getattr(e,"status_code",None) is None:raise
        print("group selection/freeze/stale/recompute checks OK")

if __name__=="__main__":
    check_against_enumeration();check_unique_and_degenerate();check_permutation_and_fingerprint();check_group_rules()
    print("contamination checks passed")
