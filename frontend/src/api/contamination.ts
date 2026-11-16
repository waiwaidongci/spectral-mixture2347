import {request} from './client';import {ContaminationGroup} from '../types/domain';
export const getContaminationGroups=(libraryId:number)=>request<ContaminationGroup[]>(`/libraries/${libraryId}/contamination-groups`);
export const createContaminationGroup=(libraryId:number,data:{code:string;name:string;note:string;member_sample_ids:number[];matrix:number[][];registration_note:string})=>request<ContaminationGroup>(`/libraries/${libraryId}/contamination-groups`,{method:'POST',body:JSON.stringify(data)});
export const addContaminationRegistration=(groupId:number,data:{member_sample_ids:number[];matrix:number[][];note:string})=>request<ContaminationGroup>(`/contamination-groups/${groupId}/registrations`,{method:'POST',body:JSON.stringify(data)});
