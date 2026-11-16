<script setup lang="ts">
import {GroupResult} from '../types/domain';
import {number,scientific} from '../utils/format';
defineProps<{group:GroupResult}>();
</script>
<template>
  <section class="group-banner">
    <div><span>串样组 / JOINT CONTAMINATION</span><h3>{{group.code}} · {{group.name}}</h3><small>成员 {{group.member_codes.join(' / ')}} · 登记 v{{group.version}}</small></div>
    <div><span>串样矩阵秩</span><b>{{group.matrix_rank}} / {{group.member_codes.length}}</b><small>零度 {{group.matrix_nullity}} · 条件数 {{scientific(group.matrix_condition_number)}}</small></div>
    <div><span>联合唯一性</span><b :class="group.unique?'supported':'warning'">{{group.unique?'唯一':'不唯一'}}</b><small>可行宽度 {{number(group.max_feasible_width,5)}} / 容差 1e−7</small></div>
    <p>{{group.uniqueness_note}}</p>
  </section>
</template>
