const {test}=require('node:test');
const assert=require('node:assert/strict');
const {webcrypto}=require('node:crypto');
const {create,USER,PASSWORD,KEYS}=require('../static/demo-auth.js');
const memory=()=>{const map=new Map();return {getItem:k=>map.get(k)||null,setItem:(k,v)=>map.set(k,v),removeItem:k=>map.delete(k)};};
const NEXT='Mau-moi-rieng!2026';
function fixture(){
  const storage=memory(),sessions=memory();let time=10000000,calls=0;
  const make=sessionStorage=>create({storage,sessionStorage,crypto:webcrypto,clock:()=>time,loadProfile:async()=>{calls++;return {athlete:{id:'sample-athlete-1',full_name:'Võ sinh mẫu 01',official_code:USER},medals:{HCV:1,HCB:0,'HCĐ':0},tournament_count:1,achievements:[{id:'sample-result-1',athletes:[{id:'sample-athlete-1'},{id:'sample-athlete-2'}]}]};}});
  const auth=make(sessions);return {storage,sessions,auth,make,advance:n=>time+=n,calls:()=>calls};
}
const login=(auth,password=PASSWORD)=>auth.request('/api/student/login',{method:'POST',body:{username:USER,password}});
const post=(auth,path,session,body)=>auth.request(path,{method:'POST',headers:{'X-CSRF-Token':session.csrf},body});
const change=(auth,s,next=NEXT)=>post(auth,'/api/password',s,{current_password:PASSWORD,password:next,confirm_password:next});

test('first login blocks data load until mandatory change',async()=>{
  const f=fixture();const s=await login(f.auth);assert.equal(true,s.user.must_change_password);assert.deepEqual([],s.user.athlete_ids);
  await assert.rejects(f.auth.request('/api/student/athletes/sample-athlete-1'),{status:403});assert.equal(0,f.calls());
  const next=await change(f.auth,s);assert.equal(false,next.user.must_change_password);assert.notEqual(s.csrf,next.csrf);
  const p=await f.auth.request('/api/student/athletes/sample-athlete-1');assert.equal(USER,p.athlete.official_code);assert.equal(1,p.achievements[0].athletes.length);
});
test('password is hashed, survives reload and old password stops working',async()=>{
  const f=fixture(),s=await login(f.auth);await change(f.auth,s);
  const saved=f.storage.getItem(KEYS.account);assert.equal(false,saved.includes(NEXT));assert.equal(false,saved.includes(PASSWORD));
  const reload=f.make(f.sessions);assert.equal(false,(await reload.request('/api/session')).user.must_change_password);
  await assert.rejects(login(reload),{status:401});assert.equal(USER,(await login(reload,NEXT)).user.username);
});
test('wrong password, reused password, missing confirmation and short password rejected',async()=>{
  const f=fixture();await assert.rejects(login(f.auth,'wrong'),{status:401});const s=await login(f.auth);
  for(const body of [{current_password:'wrong',password:NEXT,confirm_password:NEXT},{current_password:PASSWORD,password:PASSWORD,confirm_password:PASSWORD},{current_password:PASSWORD,password:'short',confirm_password:'short'},{current_password:PASSWORD,password:NEXT,confirm_password:'other'}])await assert.rejects(post(f.auth,'/api/password',s,body),{status:422});
  assert.equal(true,(await f.auth.request('/api/session')).user.must_change_password);
});
test('scope rejects second athlete and unknown result',async()=>{
  const f=fixture();await change(f.auth,await login(f.auth));
  await assert.rejects(f.auth.request('/api/student/athletes/sample-athlete-2'),{status:403});
  await assert.rejects(f.auth.request('/api/student/achievements/unknown'),{status:403});
});
test('change revokes old sessions across tabs and missing CSRF cannot change password',async()=>{
  const f=fixture(),a=await login(f.auth),other=f.make(memory());await login(other);
  await assert.rejects(f.auth.request('/api/password',{method:'POST',body:{current_password:PASSWORD,password:NEXT,confirm_password:NEXT}}),{status:403});
  await change(f.auth,a);assert.equal(null,(await other.request('/api/session')).user);
});
test('logout and expiry revoke sample session',async()=>{
  const f=fixture(),s=await login(f.auth);await post(f.auth,'/api/logout',s,{});assert.equal(null,(await f.auth.request('/api/session')).user);
  await login(f.auth);f.advance(8*3600000+1);assert.equal(null,(await f.auth.request('/api/session')).user);
});
test('reset affects sample auth only and restores mandatory change',async()=>{
  const f=fixture();await change(f.auth,await login(f.auth));f.storage.setItem('other-app','keep');f.auth.reset();
  assert.equal('keep',f.storage.getItem('other-app'));assert.equal(true,(await login(f.auth)).user.must_change_password);
});
test('eight failed attempts temporarily block sample sign-in',async()=>{
  const f=fixture();for(let i=0;i<8;i++)await assert.rejects(login(f.auth,'wrong'),{status:401});
  await assert.rejects(login(f.auth),{status:429});f.advance(900001);assert.equal(USER,(await login(f.auth)).user.username);
});
