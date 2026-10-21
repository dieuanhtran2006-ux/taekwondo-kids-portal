const {test} = require('node:test');
const assert = require('node:assert/strict');
const {randomUUID} = require('node:crypto');
const {read} = require('../static/preview-data.js');
const {validate,saveDemo,demoRows,storageKey} = require('../static/contributions.js');

const profile = (id,code) => ({athlete:{id,official_code:code,full_name:'Võ sinh mẫu trùng tên',is_sample:true},medals:{HCV:1,HCB:0,'HCĐ':0},tournament_count:1,achievement_count:1,achievements:[]});
const snapshot = {summary:{athletes:3},profiles:[profile('a','MAU-TKD-001'),profile('b','MAU-TKD-002'),profile('c','MAU-TKD-003')],achievements:[{id:'r',verification_status:'sample'}]};
const claim = overrides => ({athlete_name:'Võ sinh mẫu 01',athlete_code:'MAU-TKD-001',public_athlete_id:'sample-athlete-1',
  tournament_name:'Giải đề nghị mẫu',year:2025,event_name:'Quyền thử',discipline:'Quyền',participation_type:'Cá nhân',medal_type:'HCV',
  evidence_url:'',notes:'Ghi chú mẫu',contact:'',consent_to_review:true,website:'',client_request_id:randomUUID(),...overrides});
const memory = () => {const map=new Map();return {getItem:key=>map.get(key)||null,setItem:(key,value)=>map.set(key,value),removeItem:key=>map.delete(key)};};

test('search accepts Vietnamese without diacritics and official sample code',()=>{
  assert.equal(3,read(snapshot,'/api/public/athletes?q=vo%20sinh%20mau')['total']);
  assert.equal('a',read(snapshot,'/api/public/athletes?q=MAU-TKD-001').items[0].id);
});
test('duplicate names preserve separate records and pagination',()=>{
  const a=read(snapshot,'/api/public/athletes?q=vo%20sinh&limit=2'),b=read(snapshot,'/api/public/athletes?q=vo%20sinh&limit=2&page=2');
  assert.equal(2,a.pages);assert.equal(3,new Set([...a.items,...b.items].map(p=>p.id)).size);
});
test('blank and wildcard queries do not list profiles',()=>{
  for(const q of ['', 'A', '%25', '__'])assert.equal(0,read(snapshot,'/api/public/athletes?q='+q).total);
});
test('private and unknown paths never become a writable backend',()=>{
  for(const path of ['/api/submissions','/api/public/submissions','/api/public/evidence/file','/api/public/athletes/private'])assert.throws(()=>read(snapshot,path),{status:404});
  assert.throws(()=>read(snapshot,'/api/public/athletes?q=vo&page=bad'),{status:422});
});
test('demo saves pending claim durably and never changes medals',()=>{
  const store=memory(),before=JSON.stringify(snapshot);
  const receipt=saveDemo(store,claim());
  assert.equal('sample_saved',receipt.status);
  assert.equal('pending',demoRows(store)[0].status);
  const reload={getItem:key=>store.getItem(key)};assert.equal(receipt.receipt_id,demoRows(reload)[0].id);
  assert.equal(before,JSON.stringify(snapshot));
});
test('retry is idempotent and edited retry needs new request',()=>{
  const store=memory(),data=claim(),first=saveDemo(store,data),second=saveDemo(store,data);
  assert.equal(first.receipt_id,second.receipt_id);assert.equal(1,demoRows(store).length);
  assert.throws(()=>saveDemo(store,{...data,event_name:'Khác'}));
});
test('sample intake refuses real identity and discards contact',()=>{
  const store=memory();assert.throws(()=>saveDemo(store,claim({athlete_name:'Tên thật'})));
  saveDemo(store,claim({contact:'DO-NOT-STORE'}));assert.equal('',demoRows(store)[0].data.contact);
  assert.equal(false,store.getItem(storageKey).includes('DO-NOT-STORE'));
});
test('unsafe URLs, missing consent and invalid year rejected',()=>{
  for(const overrides of [{evidence_url:'javascript:alert(1)'},{evidence_url:'https://user:pass@example.org'},{consent_to_review:false},{year:0},{medal_type:'GOLD'},{website:'spam'}])assert.throws(()=>validate(claim(overrides)));
});
test('storage failure cannot produce a successful receipt',()=>{
  const store={getItem:()=>null,setItem:()=>{throw new Error('Quota exceeded');}};
  assert.throws(()=>saveDemo(store,claim()),/Quota/);
});
test('clear removes only test submissions and corrupted data is reported',()=>{
  const store=memory();saveDemo(store,claim());store.setItem('other-app','keep');store.removeItem(storageKey);
  assert.deepEqual([],demoRows(store));assert.equal('keep',store.getItem('other-app'));
  store.setItem(storageKey,'bad json');assert.throws(()=>demoRows(store),/bị lỗi/);
});
