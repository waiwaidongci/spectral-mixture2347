<script setup lang="ts">
import {Endmember,SampleResult} from '../types/domain';
import {percent} from '../utils/format';
import DataTable from './common/DataTable.vue';
const props=defineProps<{endmembers:Endmember[];sample:SampleResult}>();
const unique=()=>props.sample.unique!==false;
</script>
<template>
  <DataTable v-if="unique()" :head="['端元','点估计配比','条件2.5%分位','条件97.5%分位']">
    <tr v-for="(e,i) in endmembers" :key="e.code"><td><span :class="['pigment','color-'+i]"/>{{e.name}}</td><td>{{percent(sample.point_fit.weights[i])}}</td><td>{{sample.lower?percent(sample.lower[i]):'—'}}</td><td>{{sample.upper?percent(sample.upper[i]):'—'}}</td></tr>
  </DataTable>
  <DataTable v-else :head="['端元','点估计（不可视为唯一）','可行下界','可行上界']">
    <tr v-for="(e,i) in endmembers" :key="e.code"><td><span :class="['pigment','color-'+i]"/>{{e.name}}</td><td>{{percent(sample.point_fit.weights[i])}}</td><td>{{sample.feasible_lower?percent(sample.feasible_lower[i]):'—'}}</td><td>{{sample.feasible_upper?percent(sample.feasible_upper[i]):'—'}}</td></tr>
  </DataTable>
</template>
