<script setup lang="ts">
import {computed,ref} from 'vue';
import {useRoute} from 'vue-router';
import {useResearchData} from '../hooks/useResearch';
import RunSummary from '../components/RunSummary.vue';
import SpectralPlot from '../components/SpectralPlot.vue';
import WeightsTable from '../components/WeightsTable.vue';
import GroupPanel from '../components/GroupPanel.vue';
import DataTable from '../components/common/DataTable.vue';
import StatusBadge from '../components/common/StatusBadge.vue';
import Notice from '../components/common/Notice.vue';
import {number,scientific} from '../utils/format';
const s=useResearchData(true),route=useRoute(),selected=ref(Number(route.query.run)||0),sampleId=ref(0);
const run=computed(()=>s.runs.find(r=>r.id===selected.value)||s.runs[0]);
const sample=computed(()=>run.value?.result.samples?.find(x=>x.sample_id===sampleId.value)||run.value?.result.samples?.[0]);
const group=computed(()=>run.value?.result.contamination_groups?.find(g=>g.code===sample.value?.group_code)||null);
</script>
<template>
  <div class="page results-page">
    <div class="page-title"><div><p class="eyebrow">COMPOSITION & RESIDUAL / 04</p><h1>配比与残差<span>一份数值结果，保留它的可辨识性边界。</span></h1></div><RouterLink class="outline" :to="'/notes'+(run?'?run='+run.id:'')">记录复配建议 →</RouterLink></div>
    <Notice :message="s.error" @retry="s.refresh"/>
    <div class="run-picker"><label>解混档案<select aria-label="解混档案" :value="run?.id||''" @change="selected=Number(($event.target as HTMLSelectElement).value);sampleId=0"><option v-for="r in s.runs" :key="r.id" :value="r.id">#{{r.id}} / {{r.name}} / {{r.status}}</option></select></label><StatusBadge v-if="run" :status="run.status"/></div>
    <template v-if="run?.status==='completed'&&sample">
      <RunSummary :run="run"/>
      <label>当前混合样本<select aria-label="当前混合样本" v-model.number="sampleId"><option :value="0">{{run.result.samples[0].code}} / {{run.result.samples[0].name}}</option><option v-for="x in run.result.samples.slice(1)" :key="x.sample_id" :value="x.sample_id">{{x.code}} / {{x.name}}</option></select></label>
      <div v-if="run.stale_groups?.length" class="notice">本研究的串样依据已过期：{{run.stale_groups.map(g=>`${g.code} 冻结 v${g.frozen_version} / 当前 v${g.current_version}`).join('；')}}。运行结果仍按创建时冻结的依据展示，旧导出也保留原依据；如需按最新登记重算，请由研究员从原始观测新建重算。</div>
      <GroupPanel v-if="group" :group="group"/>
      <SpectralPlot :library="run.result.library" :endmembers="run.result.endmembers" :sample="sample"/>
      <div class="residual-summary">
        <div><span>RSS</span><b>{{scientific(sample.point_fit.rss)}}</b></div>
        <div><span>RMSE / 反射率</span><b>{{number(sample.point_fit.rmse,5)}}</b></div>
        <div><span>KKT活动误差</span><b>{{scientific(sample.point_fit.active_stationarity_error)}}</b></div>
        <strong :class="sample.high_residual?'warning':'supported'">{{sample.high_residual?'残差高于3σ参考，需查失配':'残差未超3σ参考，仍需复配验证'}}</strong>
      </div>
      <div v-if="sample.unique===false" class="notice">该样本属于串样组 {{sample.group_code}}，联合约束下配方不唯一；下表给出各颜料的可行上下界，不把它们当作唯一配方。{{sample.interval_note}}</div>
      <WeightsTable :endmembers="run.result.endmembers" :sample="sample"/>
      <p class="conditional-note">{{sample.interval_note}}</p>
      <div class="section-heading"><h2>波段残差明细</h2><span>观测 − 联合约束重建</span></div>
      <DataTable :head="['波长 / nm','观测反射率','重建反射率','残差']"><tr v-for="(wave,i) in run.result.library.wavelengths" :key="wave"><td>{{wave}}</td><td>{{number(sample.observed[i],5)}}</td><td>{{number(sample.point_fit.reconstructed[i],5)}}</td><td>{{number(sample.point_fit.residual[i],5)}}</td></tr></DataTable>
      <div class="section-heading"><h2>条件重拟合抽样</h2><span v-if="sample.unique!==false">展示前10次，API保存全部{{sample.repeats}}次</span><span v-else>串样关系退化，仅保存整组重拟合RSS</span></div>
      <DataTable v-if="sample.replicate_weights.length" :head="['重复',...run.result.endmembers.map(e=>e.name),'RSS']"><tr v-for="(w,j) in sample.replicate_weights.slice(0,10)" :key="j"><td>{{j+1}}</td><td v-for="(v,i) in w" :key="i">{{number(v,5)}}</td><td>{{scientific(sample.replicate_rss[j])}}</td></tr></DataTable>
      <DataTable v-else :head="['重复','整组RSS']"><tr v-for="(v,j) in sample.replicate_rss.slice(0,10)" :key="j"><td>{{j+1}}</td><td>{{scientific(v)}}</td></tr></DataTable>
      <p class="caption">{{run.result.assumptions}}</p>
      <p class="fingerprint">算法 {{run.result.algorithm_version||'simplex-nullspace-kkt-gaussian-v2'}} · 输入SHA256 {{run.result.input_hash}}</p>
    </template>
    <div v-else-if="run" class="pending"><h2>{{run.status==='failed'?'研究未能完成':'后台正在枚举支持集与条件重拟合'}}</h2><p>{{run.error||'独立worker执行Python计算，本页每2秒更新。'}}</p></div>
    <p v-else class="empty">尚无解混研究，请先选择可辨识光谱库。</p>
  </div>
</template>
