/* Isolated tests of the original UI adapters. Browser rendering is checked separately. */
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const root=require('node:path').resolve(__dirname,'..');
const fixture=JSON.parse(fs.readFileSync(root+'/docs/live_validation.json','utf8')).forecast;
fixture.city='Mandalay, Myanmar';fixture.stale=false;fixture.warnings=[];
const meta={city:fixture.city,aqi_standard:fixture.aqi_standard,calculation_version:fixture.calculation_version};
class Element {
  constructor(){this.style={};this.children=[];this.attributes={};this.textContent='';this._html='';this.listeners={};this.classes=new Set();this.classList={contains:c=>this.classes.has(c),add:c=>this.classes.add(c),remove:c=>this.classes.delete(c),toggle:(c,on)=>{on=on===undefined?!this.classes.has(c):on;on?this.classes.add(c):this.classes.delete(c);return on;}};}
  set innerHTML(value){this._html=value;this.children=[];}
  get innerHTML(){return this._html;}
  appendChild(el){this.children.push(el);}
  querySelector(){return this.button||(this.button=new Element());}
  addEventListener(name,fn){this.listeners[name]=fn;}
  setAttribute(name,val){this.attributes[name]=val;}
  removeAttribute(name){delete this.attributes[name];}
  focus(){document.activeElement=this;}
}
const elements=new Map();
const document={body:new Element(),hidden:false,activeElement:null,listeners:{},getElementById:id=>{if(!elements.has(id))elements.set(id,new Element());return elements.get(id);},createElement:()=>new Element(),addEventListener:(name,fn)=>document.listeners[name]=fn};
const storage=new Map(),timers=[],errors=[];
const localStorage={getItem:key=>storage.get(key)??null,setItem:(key,value)=>storage.set(key,value)};
let time=Date.parse('2026-10-10T08:00:00Z'),requests=0,outage=false;
class TestDate extends Date {constructor(...args){super(...(args.length?args:[time]));}static now(){return time;}}
class Chart {constructor(canvas,config){this.data=config.data;this.options=config.options;this.id=++Chart.count;this.updates=0;}update(){this.updates++;}}Chart.count=0;
const context=vm.createContext({document,localStorage,Chart,Date:TestDate,Intl,Number,Math,Set,Promise,AbortSignal,console:{error:(...args)=>errors.push(args),warn:(...args)=>errors.push(args)},setInterval:(fn,ms)=>{timers.push({fn,ms});return timers.length;},window:{setInterval:(fn,ms)=>{timers.push({fn,ms});return timers.length;},addEventListener:()=>{}},fetch:async path=>{requests++;return {ok:!outage,json:async()=>outage?{error:'Test connection unavailable'}:path.includes('latest')?{...meta,data:fixture.current}:fixture};}});
const run=code=>vm.runInContext(code,context);
(async()=>{
  vm.runInContext(fs.readFileSync(root+'/static/clock.js','utf8'),context);
  vm.runInContext(fs.readFileSync(root+'/static/app.js','utf8'),context);
  await new Promise(resolve=>setImmediate(resolve));
  for(const [input,expected] of [
    ['2026-10-10T00:00:00+06:30','10 Oct 2026, 12:00 AM'],
    ['2026-10-10T12:00:00+06:30','10 Oct 2026, 12:00 PM'],
    ['2026-10-10T01:00:00+06:30','10 Oct 2026, 1:00 AM'],
    ['2026-10-10T13:00:00+06:30','10 Oct 2026, 1:00 PM'],
    ['2026-10-10T06:30:00Z','10 Oct 2026, 1:00 PM']])assert.equal(run(`formatTime(${JSON.stringify(input)})`),expected);
  assert.equal(run('formatTime("2026-10-10T13:00:00")'),'—');
  assert.match(document.getElementById('liveClock').innerHTML,/2:30:00 PM/);
  assert.equal(document.getElementById('currentAQI').textContent,'68.0');
  assert.equal(document.getElementById('co').textContent,'0.281 mg/m³');
  for(const h of [1,6,12,24])assert.equal(document.getElementById('aqi'+h).textContent,fixture.forecasts[h-1].predicted_cpcb_aqi.toFixed(1));
  assert.equal(document.getElementById('forecastTableBody').children.length,24);
  assert.ok(document.getElementById('forecastTableBody').children.every(row=>/AM|PM/.test(row.innerHTML)));
  assert.equal(run('forecastChart.data.datasets[0].data.length'),24);
  assert.match(run('forecastChart.options.plugins.tooltip.callbacks.title([{dataIndex:0}])'),/2:00 PM/);
  assert.equal(Chart.count,1);assert.equal(requests,2);
  const poll=timers.find(t=>t.ms===300000);assert.ok(poll);
  time+=300000;await poll.fn();
  assert.equal(requests,4);assert.equal(Chart.count,1);assert.ok(run('forecastChart.updates')>=1);
  await run('autoRefreshPrediction()');assert.equal(requests,4); // focus event coalescing
  const theme=document.getElementById('themeToggle');theme.listeners.click();
  assert.ok(document.body.classList.contains('light-mode'));assert.equal(storage.get('aqi-theme'),'light');assert.equal(Chart.count,1);
  document.getElementById('cat1').onclick();
  assert.ok(document.getElementById('precautionModal').classList.contains('show'));
  assert.match(document.getElementById('precautionMeta').textContent,/2:00 PM/);
  document.getElementById('precautionClose').listeners.click();assert.ok(!document.getElementById('precautionModal').classList.contains('show'));
  document.getElementById('currentCategory').onclick();assert.match(document.getElementById('precautionAQI').textContent,/Current AQI: 68.0/);run('closePrecautionModal()');
  document.getElementById('forecastTableBody').children[0].button.listeners.click();assert.ok(document.getElementById('precautionModal').classList.contains('show'));run('closePrecautionModal()');
  outage=true;time+=300000;await poll.fn();
  assert.equal(document.getElementById('forecastTableBody').children.length,24);
  assert.ok(document.getElementById('dataFreshness').classList.contains('stale'));
  assert.equal(Chart.count,1);assert.ok(document.body.classList.contains('light-mode'));
  run('displayCurrent({aqi:null,timestamp:null})');assert.equal(document.getElementById('currentAQI').textContent,'—');assert.equal(document.getElementById('currentCategory').onclick,null);
  vm.runInContext(fs.readFileSync(root+'/static/precautions.js','utf8'),context);
  assert.ok(document.body.classList.contains('light'));document.getElementById('theme').onclick();assert.equal(storage.get('aqi-theme'),'dark');
  assert.equal(errors.length,0);
  console.log('PASS: 12-hour Myanmar times, current AQI/CO conversion, four cards, 24 rows, Chart update reuse/tooltips, modal clicks, theme persistence, 5-minute polling/coalescing, stale retention, null/error handling, precautions theme.');
})().catch(error=>{console.error(error);process.exitCode=1;});
