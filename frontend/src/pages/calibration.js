import {timing,calibration} from '../api/entities.js';
import {workspace} from '../stores/workspace.js';
import {session} from '../stores/session.js';
import {heading} from '../components/common/shell.js';
import {esc,fmt,date,notify} from '../utils/dom.js';
import {submit} from '../hooks/forms.js';
import {parseCSV} from '../utils/csv.js';
import {TimingBatchStatus,TimingRecordStatus} from '../constants/enums.js';
const badge=v=>'<span class="status '+esc(v)+'">'+esc(TimingBatchStatus[v]||v)+'</span>';
const recBadge=v=>'<span class="status '+esc(v)+'">'+esc(TimingRecordStatus[v]||v)+'</span>';
const tick=v=>fmt(v);
function detailText(d){
 if(!d||!d.before)return '';
 const seg=(label,parts)=>'<div>'+label+'：'+parts.map(p=>'['+fmt(p.start)+'–'+fmt(p.end)+'] × '+p.rate+' = '+fmt(p.seconds)+' 秒').join('；')+'</div>';
 return '<details class="tick-detail"><summary>分段换算明细（'+((d.before||[]).length+(d.after||[]).length)+' 段）</summary>'+seg('原路线',d.before||[])+seg('新路线',d.after||[])+'</details>';
}
function recordRow(r){
 const info=r.status==='blocked'?'<span class="blocked-note">'+esc(r.error)+'</span>':r.status==='converted'?detailText(r.detail):'';
 return '<tr><td>'+r.row_no+'</td><td>'+esc(r.operator)+'</td><td>'+esc(r.team)+'</td><td>'+esc(r.device)+'</td><td>'+esc(r.boot_no)+'</td>'
  +'<td>'+tick(r.before_start)+' – '+tick(r.before_end)+'</td><td>'+tick(r.after_start)+' – '+tick(r.after_end)+'</td>'
  +'<td>'+recBadge(r.status)+(r.basis_version?' <small>v'+r.basis_version+'</small>':'')+'</td>'
  +'<td>'+(r.status==='converted'?fmt(r.before_seconds)+' / '+fmt(r.after_seconds):'—')+'</td><td>'+info+'</td></tr>';
}
function batchDetail(b){
 const canWrite=session.user.role!=='viewer';
 const head='<div class="section-title"><h2>'+esc(b.name)+'</h2><span>'+badge(b.status)+'　已换算 '+b.converted_count+'/'+b.total_count+(b.blocked_count?' · 阻塞 '+b.blocked_count:'')+'</span></div>';
 const actions=b.status==='released'
  ?'<div class="batch-actions"><a class="button small" href="#/datasets">查看已放行数据批次 ↗</a><span class="hint-inline">放行于 '+date(b.released_at)+'，原测时与校时依据已留存</span></div>'
  :'<div class="batch-actions"><button class="button small" id="convert-batch" '+(canWrite?'':'disabled')+'>换算 / 继续 ↻</button><button class="primary small" id="release-batch" '+(canWrite?'':'disabled')+'>放行生成分析批次 ↗</button></div>';
 const cols='<tr><th>行</th><th>作业员</th><th>小组</th><th>设备</th><th>开机批号</th><th>原路线刻度</th><th>新路线刻度</th><th>状态</th><th>换算秒 前/后</th><th>阻塞区间 / 换算明细</th></tr>';
 const rows=(b.records||[]).map(recordRow).join('');
 const tableHtml='<div class="table-wrap"><table><thead>'+cols+'</thead><tbody>'+rows+'</tbody></table></div>';
 const snap=b.status==='released'&&b.basis_snapshot&&Object.keys(b.basis_snapshot).length
  ?'<div class="section-title"><h2>放行时采用的校时依据</h2><span>快照留存，不随后续登记改变</span></div>'+Object.values(b.basis_snapshot).map(s=>'<div class="basis-card"><strong>'+esc(s.device)+' · '+esc(s.boot_no)+'</strong> <small>依据版本 v'+s.version+'</small><div class="tick-detail">'+s.segments.map(x=>'['+fmt(x.start_tick)+'–'+fmt(x.end_tick)+'] × '+x.seconds_per_tick+' 秒/刻度').join('；')+'</div></div>').join('')
  :'';
 return head+actions+tableHtml+snap;
}
function basisCard(b){
 const canWrite=session.user.role!=='viewer';
 const rows=b.segments.map(s=>'<tr class="'+(s.conflict?'seg-conflict':'')+'"><td>'+tick(s.start_tick)+'</td><td>'+tick(s.end_tick)+'</td><td>'+s.seconds_per_tick+'</td><td>v'+s.version+'</td><td>'+esc(s.created_by)+'</td><td><button class="text-button" data-segment="'+s.id+'" '+(canWrite?'':'disabled')+'>作废</button></td></tr>').join('');
 return '<div class="basis-card"><div class="section-title"><h2>'+esc(b.device)+' · '+esc(b.boot_no)+'</h2><span>依据版本 v'+b.version+' · 更新于 '+date(b.updated_at)+(b.conflict?' · <em class="blocked-note">存在重叠冲突</em>':'')+'</span></div>'
  +(b.segments.length?'<div class="table-wrap"><table><thead><tr><th>起始刻度</th><th>结束刻度</th><th>每刻度秒数</th><th>登记版本</th><th>登记人</th><th></th></tr></thead><tbody>'+rows+'</tbody></table></div>':'<p class="hint">该设备与开机批号下暂无有效区间。</p>')+'</div>';
}
export async function calibrationPage(){
 const [batches,bases]=await Promise.all([timing.list(),calibration.bases()]);
 workspace.timingBatches=batches;workspace.bases=bases;
 const m=workspace.meta,t=m.timing||{record_columns:[],segment_columns:[],note:''};
 let selected=null;
 if(batches.length){
   const id=workspace.timingBatch&&batches.some(b=>b.id===workspace.timingBatch)?workspace.timingBatch:batches[0].id;
   workspace.timingBatch=id;selected=await timing.get(id);
 }
 return heading('03 / TIMING CALIBRATION','设备测时校准',t.note||'采集器换电重启后刻度归零，刻度快慢随校时段改变；按设备与开机批号登记校时依据，分段换算为秒并全批通过后才放行。')
 +'<div class="calibration-grid"><section class="panel"><div class="section-title"><h2>待校准批次</h2><span>'+batches.length+' 批</span></div><div class="batch-list">'
 +batches.map(b=>'<button class="batch-item" data-batch="'+b.id+'"><strong>'+esc(b.name)+'</strong><span>'+badge(b.status)+'　'+b.converted_count+'/'+b.total_count+' 已换算'+(b.blocked_count?' · 阻塞 '+b.blocked_count:'')+'</span><small>'+esc(b.source)+' · '+date(b.created_at)+'</small></button>').join('')
 +'</div><div class="section-title"><h2>接入设备测时</h2></div><form id="timing-form"><label>批次名称<input name="name" required minlength="2" placeholder="例如：12 月设备测时批次"></label><label>上传 CSV 或 JSON<input type="file" id="timing-file" accept=".json,.csv"></label><label>记录 JSON<textarea name="records" rows="6" placeholder="粘贴 JSON 数组，或先选择上方文件" required></textarea></label><p class="hint">字段：'+t.record_columns.map(c=>esc(c.key)+' / '+esc(c.label)).join('，')+'。刻度为采集器原始读数，换算在校验后逐条进行。</p><button type="submit" class="primary" '+(session.user.role==='viewer'?'disabled':'')+'>接入待校准批次</button></form></section>'
 +'<section class="panel" id="timing-detail">'+(selected?batchDetail(selected):'<div class="empty">尚无待校准批次。先在左侧接入设备测时记录。</div>')+'</section></div>'
 +'<section class="panel"><div class="section-title"><h2>校时依据</h2><span>按设备与开机批号登记刻度区间与每刻度秒数</span></div><div id="basis-list">'
 +(bases.length?bases.map(basisCard).join(''):'<div class="empty">尚未登记校时依据。登记后，缺口批次的换算会自动接续。</div>')+'</div>'
 +'<div class="section-title"><h2>登记校时区间</h2></div><form id="segment-form"><div class="parameter-grid"><label>采集设备<input name="device" required placeholder="例如：TC-02"></label><label>开机批号<input name="boot_no" required placeholder="例如：B0902"></label></div><label>刻度区间<textarea name="segments" rows="4" placeholder=\'[{"start_tick":400000,"end_tick":700000,"seconds_per_tick":0.00098}]\' required></textarea></label><p class="hint">每行或 JSON 数组登记一段：起始刻度,结束刻度,每刻度秒数。迟到数据登记后自动接续换算受影响批次；与既有区间重叠会形成冲突并阻止放行，可在上方作废。</p><button type="submit" class="primary" '+(session.user.role==='viewer'?'disabled':'')+'>登记校时依据</button></form></section>';
}
function parseSegments(text){
 text=text.trim();
 if(!text)throw new Error('请填写刻度区间');
 let list;
 if(text.startsWith('[')||text.startsWith('{')){
   const parsed=JSON.parse(text);list=Array.isArray(parsed)?parsed:[parsed];
 }else{
   list=text.split(/\n+/).filter(Boolean).map(line=>{const p=line.split(/[，,\s]+/).filter(Boolean);if(p.length!==3)throw new Error('每行需为：起始刻度,结束刻度,每刻度秒数');return{start_tick:p[0],end_tick:p[1],seconds_per_tick:p[2]};});
 }
 return list.map(s=>{const v=Array.isArray(s)?{start_tick:s[0],end_tick:s[1],seconds_per_tick:s[2]}:s;const out={start_tick:Number(v.start_tick),end_tick:Number(v.end_tick),seconds_per_tick:Number(v.seconds_per_tick)};if(Object.values(out).some(x=>!isFinite(x)))throw new Error('刻度区间必须为数值');return out;});
}
export function bindCalibration(refresh){
 const fileInput=document.querySelector('#timing-file');
 if(fileInput)fileInput.addEventListener('change',async e=>{try{const file=e.target.files[0];if(!file)return;const text=await file.text(),records=file.name.endsWith('.csv')?parseCSV(text):JSON.parse(text);document.querySelector('#timing-form [name=records]').value=JSON.stringify(records,null,2);}catch(error){notify(error.message,true);}});
 document.querySelectorAll('[data-batch]').forEach(btn=>btn.onclick=async()=>{try{workspace.timingBatch=Number(btn.dataset.batch);const b=await timing.get(workspace.timingBatch);document.querySelector('#timing-detail').innerHTML=batchDetail(b);bindDetail(refresh);}catch(error){notify(error.message,true);}});
 const timingForm=document.querySelector('#timing-form');
 if(timingForm)submit(timingForm,async f=>{const b=await timing.create({name:f.get('name'),source:fileInput&&fileInput.files[0]?fileInput.files[0].name:'manual.json',records:JSON.parse(f.get('records'))});workspace.timingBatch=b.id;notify('测时批次已接入待校准区');await refresh();});
 const segForm=document.querySelector('#segment-form');
 if(segForm)submit(segForm,async f=>{const r=await calibration.register({device:f.get('device'),boot_no:f.get('boot_no'),segments:parseSegments(f.get('segments'))});const n=(r.resumed||[]).reduce((a,x)=>a+x.converted,0);notify('校时依据已登记为 v'+r.basis.version+(r.resumed&&r.resumed.length?'，已接续换算 '+r.resumed.length+' 个批次（新换算 '+n+' 条）':''));await refresh();});
 document.querySelectorAll('[data-segment]').forEach(btn=>btn.onclick=async()=>{try{const r=await calibration.remove(btn.dataset.segment);notify('区间已作废，依据版本升为 v'+r.basis.version+'；受影响批次已重新换算');await refresh();}catch(error){notify(error.message,true);}});
 bindDetail(refresh);
}
function bindDetail(refresh){
 const convertBtn=document.querySelector('#convert-batch');
 if(convertBtn)convertBtn.onclick=async()=>{try{const r=await timing.convert(workspace.timingBatch);notify('换算完成：新换算 '+r.stats.converted+' 条，阻塞 '+r.stats.blocked+' 条，跳过 '+r.stats.skipped+' 条');await refresh();}catch(error){notify(error.message,true);await refresh();}};
 const releaseBtn=document.querySelector('#release-batch');
 if(releaseBtn)releaseBtn.onclick=async()=>{try{const r=await timing.release(workspace.timingBatch);notify(r.created?'全批通过，已放行生成数据批次「'+r.dataset.name+'」':'批次此前已放行，未重复生成');await refresh();}catch(error){notify(error.message,true);await refresh();}};
}
