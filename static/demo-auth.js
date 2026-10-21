/* Sample-only adapter. It is never an authentication boundary for real records. */
(function(root){
  'use strict';
  const USER='MAU-TKD-001', PASSWORD='TKD-Mau!2026', ATHLETE='sample-athlete-1';
  const KEYS={account:'tkd.sample.account.v1',session:'tkd.sample.session.v1',attempts:'tkd.sample.attempts.v1'};
  const fail=(message,status=422,code)=>{const e=new Error(message);e.status=status;if(code)e.details={code};throw e;};
  function create({storage,sessionStorage,crypto,loadProfile,clock=()=>Date.now()}){
    const hex=bytes=>Array.from(bytes,b=>b.toString(16).padStart(2,'0')).join('');
    async function digest(password,salt){
      if(typeof password!=='string'||password.length>256)return '';
      const key=await crypto.subtle.importKey('raw',new TextEncoder().encode(password),'PBKDF2',false,['deriveBits']);
      const bits=await crypto.subtle.deriveBits({name:'PBKDF2',hash:'SHA-256',iterations:600000,salt:new TextEncoder().encode(salt)},key,256);
      return hex(new Uint8Array(bits));
    }
    async function account(){
      const raw=storage.getItem(KEYS.account);
      if(raw){const row=JSON.parse(raw);if(typeof row.hash!=='string'||typeof row.salt!=='string'||typeof row.generation!=='string')fail('Dữ liệu mẫu bị lỗi. Hãy đặt lại tài khoản mẫu.');return row;}
      const salt=crypto.randomUUID();
      const row={salt,hash:await digest(PASSWORD,salt),mustChange:true,generation:crypto.randomUUID()};
      storage.setItem(KEYS.account,JSON.stringify(row));return row;
    }
    function session(row){
      let s;try{s=JSON.parse(sessionStorage.getItem(KEYS.session)||'null');}catch{return null;}
      if(!s||s.expires<=clock()||s.generation!==row.generation||!s.token||!s.csrf){sessionStorage.removeItem(KEYS.session);return null;}
      return s;
    }
    function response(row,s){return {configured:true,csrf:s?.csrf||'',user:s?{id:'sample-account-1',username:USER,role:'viewer',must_change_password:row.mustChange,athlete_ids:row.mustChange?[]:[ATHLETE],branch_ids:[]}:null};}
    function start(row){const s={token:crypto.randomUUID(),csrf:crypto.randomUUID(),expires:clock()+8*3600000,generation:row.generation};sessionStorage.setItem(KEYS.session,JSON.stringify(s));return response(row,s);}
    async function request(path,{method='GET',body={},headers={}}={}){
      const row=await account();let s=session(row);
      if(path==='/api/session'&&method==='GET')return response(row,s);
      if(path==='/api/student/login'&&method==='POST'){
        let attempts=JSON.parse(sessionStorage.getItem(KEYS.attempts)||'[]').filter(t=>t>clock()-900000);
        if(attempts.length>=8)fail('Quá nhiều lần đăng nhập sai. Thử lại sau 15 phút.',429);
        const valid=await digest(body.password,row.salt)===row.hash;
        if(String(body.username||'').trim().toUpperCase()!==USER||!valid){attempts.push(clock());sessionStorage.setItem(KEYS.attempts,JSON.stringify(attempts));fail('Mã võ sinh hoặc mật khẩu không đúng.',401);}
        sessionStorage.removeItem(KEYS.attempts);return start(row);
      }
      if(!s)fail('Vui lòng đăng nhập.',401);
      if(method!=='GET'&&headers['X-CSRF-Token']!==s.csrf)fail('Phiên thao tác không hợp lệ. Hãy tải lại trang.',403);
      if(path==='/api/logout'&&method==='POST'){sessionStorage.removeItem(KEYS.session);return {ok:true};}
      if(path==='/api/password'&&method==='POST'){
        if(await digest(body.current_password,row.salt)!==row.hash)fail('Mật khẩu hiện tại chưa đúng.');
        if(typeof body.password!=='string'||body.password.length<12||body.password.length>256)fail('Mật khẩu cần từ 12 đến 256 ký tự.');
        if(body.password!==body.confirm_password)fail('Mật khẩu mới và nhập lại chưa khớp.');
        if(body.password===body.current_password||body.password.toUpperCase()===USER)fail('Mật khẩu mới phải khác mật khẩu hiện tại và mã đăng nhập.');
        const salt=crypto.randomUUID(),hash=await digest(body.password,salt);
        if((await account()).generation!==row.generation)fail('Tài khoản đã thay đổi. Hãy đăng nhập lại.',409);
        const next={salt,hash,mustChange:false,generation:crypto.randomUUID(),passwordChangedAt:new Date(clock()).toISOString()};
        storage.setItem(KEYS.account,JSON.stringify(next));sessionStorage.removeItem(KEYS.session);return start(next);
      }
      if(row.mustChange)fail('Cần đổi mật khẩu lần đầu trước khi mở hồ sơ.',403,'PASSWORD_CHANGE_REQUIRED');
      if(method!=='GET')fail('Không hỗ trợ thao tác này.',405);
      if(path==='/api/student/athletes/'+ATHLETE){
        const data=await loadProfile();
        return {...data,attendance:{items:[],summary:{present:0,excused_absent:0,unexcused_absent:0},total:0,page:1,pages:1},athlete:{...data.athlete,branch_name:null,status:null},achievements:data.achievements.map(r=>({...r,athletes:r.athletes.filter(a=>a.id===ATHLETE)}))};
      }
      if(path.startsWith('/api/student/achievements/')){
        const data=await loadProfile(),r=data.achievements.find(r=>r.id===path.split('/').pop());
        if(r)return {...r,athletes:r.athletes.filter(a=>a.id===ATHLETE)};
      }
      fail('Hồ sơ hoặc thành tích nằm ngoài phạm vi được cấp quyền.',403);
    }
    function reset(){storage.removeItem(KEYS.account);sessionStorage.removeItem(KEYS.session);sessionStorage.removeItem(KEYS.attempts);}
    return {request,reset};
  }
  const api={create,USER,PASSWORD,KEYS};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;
  root.TKDStudentDemo=api;
})(typeof window!=='undefined'?window:globalThis);
