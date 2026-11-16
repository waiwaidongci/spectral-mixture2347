import hashlib
import numpy as np
from .unmix_algorithm import matrix_diagnostics
from .joint_algorithm import JointModel,joint_feasible_bounds
from .noise_algorithm import conditional_refits,joint_conditional_refits
from ..utils.fingerprint import fingerprint

ALGORITHM_VERSION="simplex-joint-contamination-gaussian-v3"
JOINT_MAX_MEMBERS=6

def _seed_for(*keys):
    digest=hashlib.sha256("|".join(str(k) for k in keys).encode()).digest()
    return np.random.SeedSequence([int.from_bytes(digest[i:i+4],"big") for i in range(0,32,4)])

def _ordered_groups(groups):
    """Canonical ordering: members by sample id, matrix rows/columns permuted alike."""
    frozen=[]
    for group in groups:
        members=list(group['member_sample_ids']);matrix=np.asarray(group['matrix'],dtype=float)
        order=sorted(range(len(members)),key=lambda i:members[i])
        frozen.append({"group_id":group['group_id'],"code":group['code'],"name":group['name'],
                       "group_note":group.get('group_note',''),"registration_id":group['registration_id'],
                       "version":group['version'],"member_sample_ids":[members[i] for i in order],
                       "matrix":[[float(matrix[r,c]) for c in order] for r in order],
                       "registration_note":group.get('registration_note',''),
                       "created_by":group['created_by'],"created_at":group['created_at']})
    return sorted(frozen,key=lambda g:min(g['member_sample_ids']))

def analyze_unmix(snapshot,noise_sigma=.005,repeats=80,seed=2026):
    library=snapshot['library'];members=sorted(snapshot['endmembers'],key=lambda e:e['code']);samples=sorted(snapshot['samples'],key=lambda s:s['code'])
    if not 1<=len(samples)<=6 or len(samples)*repeats>480:raise ValueError("选择1–6个样本，样本数×重复数不得超过480")
    if len({s['code'] for s in samples})!=len(samples):raise ValueError("混合样本编号重复")
    if type(seed) is not int or not 0<=seed<=2147483647:raise ValueError("根种子须为0–2147483647整数")
    wavelengths=np.asarray(library['wavelengths'],dtype=float)
    if wavelengths.ndim!=1 or not np.isfinite(wavelengths).all() or np.any(np.diff(wavelengths)<=0):raise ValueError("波长须有限且严格递增")
    A=np.array([e['spectrum'] for e in members],dtype=float).T
    _,diagnostics=matrix_diagnostics(A)
    if len(wavelengths)!=A.shape[0]:raise ValueError("波长与端元波段数不匹配")
    if not diagnostics['supported']:raise ValueError(diagnostics['reason'])
    groups=_ordered_groups(snapshot.get('contamination_groups') or [])
    by_id={s['id']:s for s in samples}
    assigned={sid for g in groups for sid in g['member_sample_ids']}
    if assigned-set(by_id):raise ValueError("串样组包含本次未选择的成员")
    if len(assigned)!=sum(len(g['member_sample_ids']) for g in groups):raise ValueError("同一份测量不能同时归入多个串样组")
    for group in groups:
        if len(set(group['member_sample_ids']))!=len(group['member_sample_ids']):raise ValueError(f"串样组 {group['code']} 成员重复")
    ungrouped=[s for s in samples if s['id'] not in assigned]
    sample_results=[];group_results=[]
    for group in groups:
        members_rows=[by_id[sid] for sid in group['member_sample_ids']]
        group_seed=_seed_for("group",seed,group['code'],group['version'],*(s['code'] for s in members_rows))
        try:model=JointModel(A,np.asarray(group['matrix'],dtype=float))
        except ValueError as e:raise ValueError(f"串样组 {group['code']}：{e}")
        if model.n>JOINT_MAX_MEMBERS:raise ValueError("串样组最多6份原样本")
        Y=np.array([s['observed'] for s in members_rows],dtype=float)
        fit=model.fit(Y);bounds=joint_feasible_bounds(model,fit['weights'])
        refits=joint_conditional_refits(model,Y,noise_sigma,repeats,group_seed,unique=bounds['unique'])
        group_results.append({"group_id":group['group_id'],"code":group['code'],"name":group['name'],
            "group_note":group['group_note'],"registration_id":group['registration_id'],"version":group['version'],
            "registration_note":group['registration_note'],"member_sample_ids":list(group['member_sample_ids']),
            "member_codes":[s['code'] for s in members_rows],"matrix":group['matrix'],
            "seed_key":list(group_seed.spawn_key),"unique":bounds['unique'],
            "max_feasible_width":bounds['max_width'],"matrix_rank":bounds['rank'],
            "matrix_nullity":bounds['nullity'],"matrix_condition_number":bounds['condition_number'],
            "joint_rss":fit['rss'],"joint_kkt_tolerance":fit['kkt_tolerance'],
            "joint_active_stationarity_error":fit['active_error'],
            "replicate_rss":refits['replicate_rss'],"replicate_row_rss":refits['replicate_row_rss'],
            "uniqueness_note":("串样矩阵虽可能秩亏，但联合约束仍把各原配比限定为同一可行点，按联合约束判定唯一。"
                               if bounds['unique'] else
                               "串样关系退化；联合约束下存在多个同样最优的原配比，只展示各颜料的可行上下界，不报唯一配方。")})
        for index,sample in enumerate(members_rows):
            row_weights=fit['weights'][index].tolist()
            replicate_weights=[w[index] for w in refits['replicate_weights']] if bounds['unique'] else []
            residual=np.asarray(sample['observed'],dtype=float)-fit['reconstructed'][index]
            sample_results.append({"sample_id":sample['id'],"code":sample['code'],"name":sample['name'],
                "observed":sample['observed'],"spawn_key":list(group_seed.spawn_key),
                "group_id":group['group_id'],"group_code":group['code'],"group_version":group['version'],
                "contamination_row":[float(v) for v in np.asarray(group['matrix'][index],dtype=float)],
                "contamination_effect":fit['C_weights'][index].tolist(),
                "point_fit":{"weights":row_weights,"reconstructed":fit['reconstructed'][index].tolist(),
                             "residual":residual.tolist(),"rss":float(fit['rss_rows'][index]),
                             "rmse":float(np.sqrt(fit['rss_rows'][index]/len(residual))),
                             "active_count":int(np.sum(fit['weights'][index]>1e-8)),
                             "active_stationarity_error":fit['active_error'],
                             "inactive_slack_min":fit['inactive_min'],
                             "kkt_tolerance":fit['kkt_tolerance'],
                             "supports_solved":None},
                "unique":bounds['unique'],"feasible_lower":bounds['lower'][index].tolist(),
                "feasible_upper":bounds['upper'][index].tolist(),
                "max_feasible_width":float(np.max(bounds['upper'][index]-bounds['lower'][index])),
                "replicate_weights":replicate_weights,
                "replicate_rss":[r[index] for r in refits['replicate_row_rss']],
                "replicate_group_rss":refits['replicate_rss'],
                "replicate_row_rss":[r[index] for r in refits['replicate_row_rss']],
                "lower":None if refits['lower'] is None else refits['lower'][index],
                "median":None if refits['median'] is None else refits['median'][index],
                "upper":None if refits['upper'] is None else refits['upper'][index],
                "noise_sigma":noise_sigma,"repeats":repeats,"degenerate_noise":noise_sigma==0,
                "high_residual":float(np.sqrt(fit['rss_rows'][index]/len(residual)))>max(3*noise_sigma,1e-8),
                "interval_note":("串样组联合约束唯一时，对整组观测加独立Gaussian扰动后重新联合拟合；"
                                 "分位范围条件于固定端元、给定sigma与登记串样比例，不覆盖端元误差。"
                                 if bounds['unique'] else
                                 "串样关系退化，未报唯一配方；可行上下界来自同一最优残差面上的线性规划，"
                                 "条件重复只记录整组重拟合RSS，不产生单份配比分位。")})
    for sample in ungrouped:
        child=_seed_for("sample",seed,sample['code'])
        refits=conditional_refits(A,sample['observed'],noise_sigma,repeats,child)
        sample_results.append({"sample_id":sample['id'],"code":sample['code'],"name":sample['name'],
            "observed":sample['observed'],"spawn_key":list(child.spawn_key),
            "group_id":None,"group_code":None,"group_version":None,"contamination_row":None,
            "contamination_effect":None,"point_fit":refits['point_fit'],"unique":True,
            "feasible_lower":None,"feasible_upper":None,"max_feasible_width":None,
            "replicate_weights":refits['replicate_weights'],"replicate_rss":refits['replicate_rss'],
            "replicate_group_rss":None,"replicate_row_rss":None,
            "lower":refits['lower'],"median":refits['median'],"upper":refits['upper'],
            "noise_sigma":noise_sigma,"repeats":repeats,"degenerate_noise":noise_sigma==0,
            "high_residual":refits['point_fit']['rmse']>max(3*noise_sigma,1e-8),
            "interval_note":refits['interval_note']})
    sample_results.sort(key=lambda r:r['code'])
    canonical={"library":library,"endmembers":members,"samples":samples,"contamination_groups":groups}
    return {"algorithm_version":ALGORITHM_VERSION,"library":library,"endmembers":members,"samples":sample_results,
            "contamination_groups":group_results,"diagnostics":diagnostics,
            "noise_sigma":noise_sigma,"repeats":repeats,"seed":seed,"input_snapshot":canonical,
            "input_hash":fingerprint({"method":ALGORITHM_VERSION,"snapshot":canonical,"noise_sigma":noise_sigma,"repeats":repeats,"seed":seed}),
            "assumptions":"固定校准端元的线性混合；每份原样本权重非负且和为1。串样按登记矩阵C联合建模：观测=C·原配方·Aᵀ；C退化时仍按联合约束判断唯一性，不通过求逆制造唯一配方。噪声在各波段独立同方差Gaussian，sigma由用户给定；高残差只提示失配，不是噪声或成分真实性检验。",
            "quantile_note":"分位范围是条件扰动情景，不是配比真值的覆盖保证；串样组重复扰动整组观测后联合重拟合。",
            "feasibility_tolerance":1e-10,"condition_limit":1e6,"joint_limits":{"max_members":JOINT_MAX_MEMBERS}}
