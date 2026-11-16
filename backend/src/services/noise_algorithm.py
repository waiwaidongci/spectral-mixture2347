import math
import numpy as np
from .unmix_algorithm import fit_simplex

def conditional_refits(A,y,noise_sigma=.005,repeats=80,seed=2026):
    if type(noise_sigma) not in (int,float) or not 0<=noise_sigma<=.2 or not math.isfinite(noise_sigma):raise ValueError("sigma必须是[0,.2]内有限反射率单位，0表示无扰动")
    if type(repeats) is not int or not 20<=repeats<=120:raise ValueError("条件重复须为20–120次")
    point=fit_simplex(A,y);rng=np.random.default_rng(seed);observed=np.asarray(y,dtype=float)
    weights=[];rss=[]
    for noise in rng.normal(0,noise_sigma,size=(repeats,len(observed))):
        fitted=fit_simplex(A,observed+noise);weights.append(fitted['weights']);rss.append(fitted['rss'])
    samples=np.asarray(weights)
    return {"point_fit":point,"replicate_weights":weights,"replicate_rss":rss,"lower":np.quantile(samples,.025,axis=0,method='linear').tolist(),"median":np.quantile(samples,.5,axis=0,method='linear').tolist(),"upper":np.quantile(samples,.975,axis=0,method='linear').tolist(),"noise_sigma":noise_sigma,"repeats":repeats,"degenerate_noise":noise_sigma==0,"interval_note":"2.5/97.5%分位范围条件于固定端元与给定sigma；对观测谱加独立Gaussian扰动重拟合，不覆盖端元误差，也不保证真配比覆盖。"}

def joint_conditional_refits(model,Y,noise_sigma=.005,repeats=80,seed=2026,unique=True):
    """Refit the whole registered group under the same joint constraints.

    Each replication perturbs every member observation and solves the group
    problem again, so a contaminated measurement is never un-mixed alone.
    """
    if type(noise_sigma) not in (int,float) or not 0<=noise_sigma<=.2 or not math.isfinite(noise_sigma):raise ValueError("sigma必须是[0,.2]内有限反射率单位，0表示无扰动")
    if type(repeats) is not int or not 20<=repeats<=120:raise ValueError("条件重复须为20–120次")
    rng=np.random.default_rng(seed);observed=np.asarray(Y,dtype=float);n,p=observed.shape
    weights=[];rss=[];row_rss=[];unique_flags=[]
    for noise in rng.normal(0,noise_sigma,size=(repeats,n,p)):
        fitted=model.fit(observed+noise)
        if unique:
            weights.append(fitted['weights'].tolist());unique_flags.append(True)
        rss.append(fitted['rss']);row_rss.append(fitted['rss_rows'].tolist())
    payload={"replicate_rss":rss,"replicate_row_rss":row_rss,"replicate_unique":unique_flags,
             "noise_sigma":noise_sigma,"repeats":repeats,"degenerate_noise":noise_sigma==0}
    if unique:
        samples=np.asarray(weights)
        payload.update({"replicate_weights":weights,
                        "lower":np.quantile(samples,.025,axis=0,method='linear').tolist(),
                        "median":np.quantile(samples,.5,axis=0,method='linear').tolist(),
                        "upper":np.quantile(samples,.975,axis=0,method='linear').tolist()})
    else:
        payload.update({"replicate_weights":[],"lower":None,"median":None,"upper":None})
    return payload

def joint_result(model,Y,fit,bounds):
    return {"C_weights":fit['C_weights'].tolist(),"unique":bounds['unique'],
            "feasible_lower":bounds['lower'].tolist(),"feasible_upper":bounds['upper'].tolist(),
            "max_feasible_width":bounds['max_width'],"uniqueness_tolerance":bounds['uniqueness_tolerance'],
            "matrix_rank":bounds['rank'],"matrix_nullity":bounds['nullity'],
            "matrix_condition_number":bounds['condition_number'],"weights":fit['weights'].tolist(),
            "predicted":fit['predicted'].tolist(),"reconstructed":fit['reconstructed'].tolist(),
            "residual":fit['residual'].tolist(),"rss_rows":fit['rss_rows'].tolist(),"rss":fit['rss'],
            "active_counts":fit['active_counts'],"active_stationarity_error":fit['active_error'],
            "inactive_slack_min":fit['inactive_min'],"kkt_tolerance":fit['kkt_tolerance']}
