<script setup lang="ts">
import {computed,ref,watch} from 'vue';
import {useRoute} from 'vue-router';
import {useResearchData} from '../hooks/useResearch';
import {useAuth} from '../stores/auth';
import {useAction} from '../hooks/useAction';
import {annotateSample} from '../api/samples';
import {createContaminationGroup,addContaminationRegistration} from '../api/contamination';
import LibrarySelector from '../components/LibrarySelector.vue';
import SpectralPlot from '../components/SpectralPlot.vue';
import DataTable from '../components/common/DataTable.vue';
import Notice from '../components/common/Notice.vue';
import {number,scientific} from '../utils/format';
import {ContaminationGroup} from '../types/domain';

const s=useResearchData(),auth=useAuth(),a=useAction(),route=useRoute(),selected=ref(Number(route.query.library)||0),editing=ref(0),note=ref('');
const library=computed(()=>s.libraries.find(l=>l.id===selected.value)||s.libraries[0]);
watch(()=>library.value?.id,id=>{if(id)s.loadLibrary(id)},{immediate:true});

const groupCode=ref('CG-01'),groupName=ref(''),groupNote=ref(''),members=ref<number[]>([]),matrix=ref<number[][]>([]),registrationNote=ref('');
const editingGroup=ref<ContaminationGroup|null>(null);
const canWrite=computed(()=>auth.user?.role!=='viewer');

function emptyMatrix(size:number){return Array.from({length:size},(_,i)=>Array.from({length:size},(_,j)=>i===j?1:0))}
function resizeMatrix(previous:number[],next:number[]){
  const size=next.length,source=matrix.value,old=previous
  matrix.value=Array.from({length:size},(_,i)=>Array.from({length:size},(_,j)=>{
    const oi=old.indexOf(next[i]),oj=old.indexOf(next[j])
    return oi>=0&&oj>=0&&source[oi]&&typeof source[oi][oj]==='number'?source[oi][oj]:(i===j?1:0)
  }))
}
function toggleMember(id:number,checked:boolean){
  if(editingGroup.value)return;
  const previous=[...members.value]
  const next=checked?[...members.value,id]:members.value.filter(x=>x!==id)
  members.value=next;resizeMatrix(previous,next)
}
function startEdit(group:ContaminationGroup){
  if(!group.current)return;
  editingGroup.value=group;groupCode.value=group.code;groupName.value=group.name;groupNote.value=group.note;
  members.value=[...group.current.member_sample_ids];matrix.value=group.current.matrix.map(r=>[...r]);
  registrationNote.value='';
}
function reset(){editingGroup.value=null;groupCode.value='CG-01';groupName.value='';groupNote.value='';members.value=[];matrix.value=[];registrationNote.value=''}
function submit(){
  a.execute(async()=>{
    const payload={code:groupCode.value,name:groupName.value,note:groupNote.value,member_sample_ids:members.value,matrix:matrix.value,registration_note:registrationNote.value};
    if(editingGroup.value)await addContaminationRegistration(editingGroup.value.id,{member_sample_ids:members.value,matrix:matrix.value,note:registrationNote.value});
    else await createContaminationGroup(library.value.id,payload);
    reset();await s.loadLibrary(library.value.id);
  })
}
const rowSums=computed(()=>matrix.value.map(r=>r.reduce((n,v)=>n+(Number(v)||0),0)));
const matrixValid=computed(()=>members.value.length>=2&&matrix.value.length===members.value.length&&rowSums.value.every(v=>Math.abs(v-1)<1e-6)&&matrix.value.every(r=>r.every(v=>Number.isFinite(v)&&v>=0)));
function memberCodes(group:ContaminationGroup){return group.current?.member_codes.join(' / ')||''}
async function save(){a.execute(async()=>{await annotateSample(editing.value,note.value);editing.value=0;await s.loadLibrary(library.value.id)})}
</script>
<template>
  <div class="page">
    <div class="page-title"><div><p class="eyebrow">REFERENCE & MIXTURE / 02</p><h1>端元与样本<span>可辨识性与输入波段，先于配比数值。</span></h1></div></div>
    <Notice :message="s.error||a.error.value" @retry="s.refresh"/>
    <LibrarySelector :libraries="s.libraries" :model-value="library?.id||0" @update:model-value="selected=$event"/>
    <div v-if="library" :class="['library-diagnostic',!library.supported?'warning':'']"><span>增广条件数 {{scientific(library.condition_number)}}</span><p>{{library.reason}}</p></div>
    <SpectralPlot v-if="library&&s.endmembers.length" :library="library" :endmembers="s.endmembers"/>
    <div class="section-heading"><h2>端元数值</h2><span>无量纲反射率 · 波段顺序固定</span></div>
    <DataTable :head="['端元',...(library?.wavelengths||[]).map(w=>w+'nm')]"><tr v-for="e in s.endmembers" :key="e.id"><td>{{e.name}}</td><td v-for="(v,i) in e.spectrum" :key="i">{{number(v)}}</td></tr></DataTable>

    <div class="section-heading"><h2>同库串样组</h2><span>登记各份测量中来自各原样本的比例</span></div>
    <p class="caption">串样指一份测量中混入了同库其他原样本的谱。登记矩阵的每一行表示该份测量来自各原样本的比例，行和为1；允许相互串样成环。选择任一组员做解混时，整组观测按联合约束求原配比，不会把混入谱误当成该份的原配方。</p>
    <DataTable v-if="s.groups.length" :head="['组号','名称','成员','矩阵秩','登记版本','操作']">
      <tr v-for="g in s.groups" :key="g.id">
        <td class="mono">{{g.code}}</td><td>{{g.name}}</td>
        <td class="note-cell">{{memberCodes(g)}}</td>
        <td>{{g.diagnostics?`秩 ${g.diagnostics.rank} / 零度 ${g.diagnostics.nullity}`:'—'}}</td>
        <td>v{{g.version_count}}</td>
        <td><button v-if="canWrite" class="text-link" @click="startEdit(g)">登记新版本</button></td>
      </tr>
    </DataTable>
    <p v-else class="empty">该光谱库尚未登记串样组；未分组样本照常单独解混。</p>

    <form v-if="canWrite" class="contamination-form" @submit.prevent="submit">
      <div class="form-heading"><span>CG</span><h2>{{editingGroup?'登记新版本 · '+editingGroup.code:'登记串样组'}}</h2></div>
      <div class="form-row">
        <label>组号<input aria-label="串样组号" v-model="groupCode" minlength="2" maxlength="40" :disabled="!!editingGroup" required/></label>
        <label>组名称<input aria-label="串样组名称" v-model="groupName" minlength="2" maxlength="120" :disabled="!!editingGroup" required/></label>
      </div>
      <label>组说明<input aria-label="串样组说明" v-model="groupNote" maxlength="1500" :disabled="!!editingGroup"/></label>
      <div class="sample-selector">
        <label v-for="sample in s.samples" :key="sample.id">
          <input type="checkbox" :value="sample.id" :checked="members.includes(sample.id)" :disabled="!!editingGroup" @change="toggleMember(sample.id,($event.target as HTMLInputElement).checked)"/>
          <span>{{sample.code}}<small>{{sample.name}}</small></span>
        </label>
      </div>
      <p class="caption">已选{{members.length}}份；串样组允许2–6份，同一份测量只能归入一个组。</p>
      <template v-if="members.length>=2">
        <p class="caption">矩阵行=测量样本（{{members.map(id=>s.samples.find(x=>x.id===id)?.code).join(' / ')}}），列=同序原样本；行和须为1。</p>
        <div class="table-wrap"><table>
          <thead><tr><th>测量 \ 原样本</th><th v-for="id in members" :key="id">{{s.samples.find(x=>x.id===id)?.code}}</th><th>行和</th></tr></thead>
          <tbody>
            <tr v-for="(id,i) in members" :key="id">
              <td>{{s.samples.find(x=>x.id===id)?.code}}</td>
              <td v-for="(_,j) in members" :key="j"><input class="matrix-input" type="number" min="0" max="1" step=".001" :aria-label="`比例 ${i}-${j}`" v-model.number="matrix[i][j]"/></td>
              <td :class="Math.abs(rowSums[i]-1)>1e-6?'warning':''">{{number(rowSums[i],4)}}</td>
            </tr>
          </tbody>
        </table></div>
      </template>
      <label>登记备注<textarea aria-label="登记备注" v-model="registrationNote" minlength="8" placeholder="说明串样来源、称量或复核依据。"/></label>
      <div class="form-row">
        <button class="primary" :disabled="a.busy.value||!matrixValid||registrationNote.length<8||!groupName">{{editingGroup?'登记新版本':'登记串样组'}}</button>
        <button v-if="editingGroup" type="button" class="outline" @click="reset">取消</button>
      </div>
    </form>

    <div class="section-heading"><h2>混合样本</h2><span>ls-pigment-spectra-202611.json</span></div>
    <form v-if="editing" class="annotation" @submit.prevent="save"><label>样本备注<input aria-label="样本备注" v-model="note" minlength="8" required/></label><button class="primary" :disabled="a.busy.value">保存备注</button><button class="outline" type="button" @click="editing=0">取消</button></form>
    <DataTable :head="['样本编号','名称','波段数','串样组','观察备注','操作']">
      <tr v-for="sample in s.samples" :key="sample.id">
        <td class="mono">{{sample.code}}</td><td>{{sample.name}}</td><td>{{sample.observed.length}}</td>
        <td>{{s.groups.find(g=>g.current?.member_sample_ids.includes(sample.id))?.code||'未分组'}}</td>
        <td class="note-cell">{{sample.note}}</td>
        <td><button v-if="canWrite" class="text-link" @click="editing=sample.id;note=sample.note">补充备注</button></td>
      </tr>
    </DataTable>
  </div>
</template>
