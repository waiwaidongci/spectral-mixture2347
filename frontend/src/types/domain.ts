export interface User{name:string;email:string;role:string}
export interface Library{id:number;code:string;name:string;description:string;wavelengths:number[];source:string;endmember_count:number;sample_count:number;contamination_group_count:number;supported:boolean;condition_number:number|null;reason:string}
export interface Endmember{id:number;library_id:number;code:string;name:string;spectrum:number[]}
export interface Sample{id:number;code:string;library_id:number;name:string;observed:number[];note:string}
export interface ContaminationRegistration{id:number;group_id:number;version:number;member_sample_ids:number[];member_codes:string[];matrix:number[][];note:string;created_by:string;created_at:string}
export interface ContaminationGroup{id:number;library_id:number;code:string;name:string;note:string;created_by:string;created_at:string;current:ContaminationRegistration|null;version_count:number;diagnostics:{rank:number;nullity:number;condition_number:number|null}|null}
export interface Fit{weights:number[];reconstructed:number[];residual:number[];rss:number;rmse:number;active_count:number;equality_error?:number;active_stationarity_error:number;inactive_slack_min:number|null;kkt_tolerance:number;supports_solved:number|null}
export interface SampleResult{sample_id:number;code:string;name:string;observed:number[];spawn_key:number[];high_residual:boolean;
  group_id?:number|null;group_code?:string|null;group_version?:number|null;
  contamination_row?:number[]|null;contamination_effect?:number[]|null;
  unique?:boolean;feasible_lower?:number[]|null;feasible_upper?:number[]|null;max_feasible_width?:number|null;
  point_fit:Fit;replicate_weights:number[][];replicate_rss:number[];replicate_row_rss?:number[][]|null;
  lower:number[]|null;median?:number[]|null;upper:number[]|null;noise_sigma:number;repeats:number;degenerate_noise:boolean;interval_note:string}
export interface GroupResult{group_id:number;code:string;name:string;group_note:string;registration_id:number;version:number;registration_note:string;member_sample_ids:number[];member_codes:string[];matrix:number[][];seed_key:number[];unique:boolean;max_feasible_width:number;matrix_rank:number;matrix_nullity:number;matrix_condition_number:number|null;joint_rss:number;joint_kkt_tolerance:number;joint_active_stationarity_error:number;replicate_rss:number[];uniqueness_note:string}
export interface Result{algorithm_version?:string;library:Library;endmembers:Endmember[];samples:SampleResult[];contamination_groups?:GroupResult[];diagnostics:{augmented_rank:number;condition_number:number|null;condition_limit:number;supported:boolean;reason:string};noise_sigma:number;repeats:number;seed:number;input_hash:string;assumptions:string;quantile_note:string;feasibility_tolerance:number;condition_limit:number}
export interface Run{id:number;name:string;library_id:number;sample_ids:number[];noise_sigma:number;repeats:number;seed:number;status:string;result:Result;error:string;owner:string;created_at:string;stale_groups?:{group_id:number;code:string;frozen_version:number;current_version:number}[]}
export interface Note{id:number;run_id:number;title:string;interpretation:string;proposal:string;status:string;owner:string;reviewer:string;review_note:string;created_at:string}
export interface Audit{id:number;actor:string;action:string;target:string;created_at:string}
