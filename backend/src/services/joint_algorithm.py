"""Joint simplex-constrained least squares for contamination-linked samples.

For a registered group of n samples, each measurement row i is modelled as a
mixture of the group originals:

    Y = C W A^T + noise

where C[i, j] is the registered fraction of original sample j found in
measurement i, A is the fixed band-by-endmember matrix, and every row of W is a
non-negative, sum-to-one original recipe.  C may be singular and may contain
cycles; identifiability is decided on the joint constraints, never by
inverting C.
"""
from functools import lru_cache
import numpy as np
from scipy.optimize import linprog
from .unmix_algorithm import matrix_diagnostics

JOINT_FEASIBILITY_TOL=1e-10
UNIQUENESS_TOL=1e-7
LP_OPTIONS={"primal_feasibility_tolerance":1e-9,"dual_feasibility_tolerance":1e-9}

@lru_cache(maxsize=8)
def _simplex_basis(size):
    if size<2:return np.zeros((size,0))
    _,_,vh=np.linalg.svd(np.ones((1,size)),full_matrices=True)
    return vh[1:].T

def contamination_diagnostics(C):
    C=np.asarray(C,dtype=float);singular=np.linalg.svd(C,compute_uv=False)
    threshold=max(C.shape)*np.finfo(float).eps*(singular[0] if singular.size else 0.)
    rank=int(np.sum(singular>threshold))
    condition=float(singular[0]/singular[-1]) if singular[-1]>0 else None
    return {"rank":rank,"nullity":C.shape[0]-rank,"condition_number":condition,"full_rank":rank==C.shape[0]}

def validate_matrix(matrix,size):
    try:C=np.asarray(matrix,dtype=float)
    except (TypeError,ValueError,OverflowError):raise ValueError("串样比例矩阵必须为有限数字")
    if C.shape!=(size,size):raise ValueError(f"串样比例矩阵须为{size}×{size}，按登记成员顺序")
    if not np.isfinite(C).all():raise ValueError("串样比例矩阵包含非有限数值")
    if np.any(C< -1e-12):raise ValueError("串样比例不得为负")
    C=np.maximum(C,0.);totals=C.sum(axis=1)
    if np.any(np.abs(totals-1)>1e-6):raise ValueError("串样比例每一行之和须为1")
    return C/totals[:,None]

class JointModel:
    """Precomputed joint design for one endmember set and contamination matrix."""
    def __init__(self,A,C):
        self.A,self.diagnostics=matrix_diagnostics(A)
        self.C=np.asarray(C,dtype=float)
        if self.C.ndim!=2 or self.C.shape[0]!=self.C.shape[1]:raise ValueError("串样比例矩阵须为方阵")
        n=self.C.shape[0]
        if np.any(self.C< -1e-12) or not np.isfinite(self.C).all() or np.any(np.abs(self.C.sum(axis=1)-1)>1e-6):
            raise ValueError("串样比例矩阵须非负且每行和为1")
        self.C=np.maximum(self.C,0.);self.C/=self.C.sum(axis=1,keepdims=True)
        p,m=self.A.shape
        if n<2:raise ValueError("串样组至少需要两份原样本")
        self.n,self.m,self.p=n,m,p
        self.Q,self.R=np.linalg.qr(self.A,mode='reduced')
        self.basis=_simplex_basis(m)
        self.origin=np.full(m,1/m)
        self.E=np.tile(self.origin,(n,1))
        rbt=self.R@self.basis
        columns=[np.outer(self.C[:,i],rbt[:,k]).reshape(-1) for i in range(n) for k in range(m-1)]
        self.M=np.column_stack(columns) if columns else np.zeros((n*m,0))
        self.const=(self.C@self.E@self.R.T).reshape(-1)
        self.H=self.M.T@self.M
        rows=[]
        for i in range(n):
            for j in range(m):
                row=np.zeros(n*(m-1))
                row[i*(m-1):(i+1)*(m-1)]=-self.basis[j,:]
                rows.append(row)
        self.Gmat=np.vstack(rows) if rows else np.zeros((0,n*(m-1)))
        self.bounds_b=np.full(n*m,1/m)
        scale=1+np.linalg.norm(self.A)**2+np.linalg.norm(self.C)**2*max(1.,np.linalg.norm(self.A))**2
        self.kkt_tolerance=float(1e-8*scale)
        self.diagnostics=dict(self.diagnostics,contamination=contamination_diagnostics(self.C),uniqueness_tolerance=UNIQUENESS_TOL)

    def _qp(self,Y,max_iter=5000):
        G=Y@self.Q
        g=self.M.T@(self.const-G.reshape(-1)) if self.M.shape[1] else np.zeros(0)
        z=np.zeros(self.M.shape[1]);active=[];iterations=0
        for _ in range(max_iter):
            iterations+=1
            if active:
                Aw=self.Gmat[active];bw=self.bounds_b[active]
                K=np.block([[self.H,Aw.T],[Aw,np.zeros((len(active),len(active)))]])
                solution,*_=np.linalg.lstsq(K,np.concatenate([-g,bw]),rcond=None)
                znew=solution[:self.M.shape[1]];multipliers=solution[self.M.shape[1]:]
            else:
                znew=np.linalg.lstsq(self.H,-g,rcond=None)[0] if self.H.size else z
                multipliers=np.zeros(0)
            slack=self.bounds_b-self.Gmat@znew
            violated=np.where(slack< -JOINT_FEASIBILITY_TOL)[0]
            if violated.size:
                direction=znew-z;change=self.Gmat@direction;step=1.
                for idx in np.where(change>1e-14)[0]:
                    candidate=(self.bounds_b[idx]-self.Gmat[idx]@z)/change[idx]
                    if candidate<step:step=candidate
                step=max(0.,min(1.,step));z=z+step*direction
                current=self.bounds_b-self.Gmat@z
                added=[idx for idx in range(len(self.bounds_b)) if current[idx]<=1e-8 and change[idx]>1e-12 and idx not in active]
                if not added:added=[int(violated[np.argmin(slack[violated])])]
                active=sorted(set(active)|set(added));continue
            z=znew
            if not active:return z,iterations
            if multipliers.min()< -1e-8:
                active.pop(int(np.argmin(multipliers)));continue
            return z,iterations
        raise ValueError("联合约束有效集未收敛；不输出不可靠配比")

    def fit(self,Y):
        Y=np.asarray(Y,dtype=float)
        if Y.shape!=(self.n,self.p) or not np.isfinite(Y).all():raise ValueError("串样组观测须为有限数字且行列数匹配")
        z,iterations=self._qp(Y)
        weights=self.origin+z.reshape(self.n,self.m-1)@self.basis.T
        if weights.min()< -1e-8:raise ValueError("联合约束解出现不可行负权重")
        weights=np.maximum(weights,0.);weights/=weights.sum(axis=1,keepdims=True)
        predicted=weights@self.A.T
        residual=self.C@predicted-Y
        gradient=2*self.C.T@residual@self.A
        active_errors=[];inactive_slacks=[];active_counts=[]
        for i in range(self.n):
            active=weights[i]>1e-8;active_counts.append(int(active.sum()))
            if active.any():
                level=float(np.mean(gradient[i,active]))
                active_errors.append(float(np.max(np.abs(gradient[i,active]-level))))
                if (~active).any():inactive_slacks.append(float(np.min(gradient[i,~active]-level)))
            else:active_errors.append(0.)
        active_error=max(active_errors) if active_errors else 0.
        inactive_min=min(inactive_slacks) if inactive_slacks else None
        if active_error>self.kkt_tolerance or (inactive_min is not None and inactive_min< -self.kkt_tolerance):
            raise ValueError("联合完整KKT最优性校验未通过；不输出不可靠配比")
        reconstructed=self.C@(weights@self.A.T)
        residual_rows=Y-reconstructed
        rss_rows=np.sum(residual_rows**2,axis=1)
        return {"weights":weights,"predicted":weights@self.A.T,"reconstructed":reconstructed,
                "residual":residual_rows,"rss_rows":rss_rows,
                "rss":float(np.sum(rss_rows)),"active_counts":active_counts,"active_error":active_error,
                "inactive_min":inactive_min,"kkt_tolerance":self.kkt_tolerance,"iterations":iterations,
                "C_weights":self.C@weights}

def joint_feasible_bounds(model,weights):
    """Every joint minimizer satisfies C W = C W*.  Bound each entry by LP.

    A is full column rank, so equal fitted predictions determine C W exactly;
    this polytope is therefore the complete optimal face (no KKT sign
    conditions are needed beyond the simplex itself).
    """
    n,m=model.n,model.m;target=model.C@weights
    Aeq=np.zeros((n+n*m,n*m))
    for i in range(n):Aeq[i,i*m:(i+1)*m]=1.
    for i in range(n):
        for j in range(m):
            for k in range(n):Aeq[n+i*m+j,k*m+j]=model.C[i,k]
    beq=np.concatenate([np.ones(n),target.reshape(-1)])
    lower=np.zeros((n,m));upper=np.ones((n,m));ok=True
    for i in range(n):
        for j in range(m):
            cost=np.zeros(n*m);cost[i*m+j]=1.
            low=linprog(cost,A_eq=Aeq,b_eq=beq,bounds=[(0.,1.)]*(n*m),method="highs",options=LP_OPTIONS)
            high=linprog(-cost,A_eq=Aeq,b_eq=beq,bounds=[(0.,1.)]*(n*m),method="highs",options=LP_OPTIONS)
            if not low.success or not high.success:
                ok=False;lower[i,j]=0.;upper[i,j]=1.;continue
            lower[i,j]=float(low.fun);upper[i,j]=float(-high.fun)
    lower=np.clip(lower,0.,1.);upper=np.clip(upper,0.,1.)
    lower=np.minimum(lower,weights);upper=np.maximum(upper,weights)
    width=float(np.max(upper-lower))
    unique=bool(ok and width<=UNIQUENESS_TOL)
    diagnostics=contamination_diagnostics(model.C)
    return {"lower":lower,"upper":upper,"unique":unique,"max_width":width,
            "lp_ok":ok,"uniqueness_tolerance":UNIQUENESS_TOL,
            "rank":diagnostics["rank"],"nullity":diagnostics["nullity"],
            "condition_number":diagnostics["condition_number"]}
