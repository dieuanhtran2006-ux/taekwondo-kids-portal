'use strict';
(() => {
  const $=(selector,root=document)=>root.querySelector(selector);
  const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const demo=document.body.dataset.preview==='sample';
  const state={session:null,csrf:'',profile:null,message:'',busy:false};
  const sampleNote=()=>demo?'<aside class="student-demo-note"><p><strong>Tài khoản mẫu · Chỉ kiểm thử trên thiết bị</strong></p><p>Đăng nhập và đổi mật khẩu được mô phỏng trên trình duyệt, không bảo vệ dữ liệu thật. Chỉ dùng mật khẩu thử nghiệm, không nhập mật khẩu đang dùng ở dịch vụ khác.</p></aside>':'';
  if(document.body.dataset.staticPreview==='1'&&!demo){$('#student-main').innerHTML='<div class="student-empty"><h1>Đăng nhập hồ sơ</h1><p>Bản tĩnh này chưa kết nối máy chủ đăng nhập. Cần triển khai backend để mở hồ sơ riêng.</p><a class="back-link" href="/">Trang đăng nhập</a></div>';return;}
  const adapter=demo?window.TKDStudentDemo.create({storage:localStorage,sessionStorage,crypto,loadProfile:async()=>{
    if(!window.TKDSampleProfile)throw new Error('Chưa tải được hồ sơ mẫu.');
    return structuredClone(window.TKDSampleProfile);
  }}):null;
  async function api(path,method='GET',body){
    const headers={Accept:'application/json'};
    if(method!=='GET'){headers['Content-Type']='application/json';headers['X-CSRF-Token']=state.csrf;}
    if(adapter)return adapter.request(path,{method,body,headers});
    let response;try{response=await fetch(path,{method,headers,credentials:'same-origin',cache:'no-store',...(body?{body:JSON.stringify(body)}:{})});}
    catch{throw new Error('Chưa kết nối được máy chủ. Vui lòng thử lại.');}
    let data;try{data=await response.json();}catch{throw new Error('Máy chủ chưa trả về dữ liệu hợp lệ.');}
    if(!response.ok){const error=new Error(data.error||'Chưa thể hoàn tất thao tác.');error.status=response.status;error.details=data.details;throw error;}
    return data;
  }
  function apply(data){state.session=data.user;state.csrf=data.csrf||'';}
  const field=(name,label,autocomplete)=>`<label>${label}<input type="password" name="${name}" autocomplete="${autocomplete}" maxlength="256" ${autocomplete==='new-password'?'minlength="12"':''} required></label>`;
  const sampleHelp=()=>demo?`<aside class="sample-account"><strong>Tài khoản kiểm thử</strong><p>Mã võ sinh: <code>${esc(window.TKDStudentDemo.USER)}</code><br>Mật khẩu ban đầu: <code>${esc(window.TKDStudentDemo.PASSWORD)}</code></p><p>Sau khi đổi, hãy dùng mật khẩu mới. Nếu quên, đặt lại tài khoản mẫu trên thiết bị này.</p><button class="secondary" type="button" data-fill-sample>Điền tài khoản mẫu</button><button class="secondary" type="button" data-reset-sample>Đặt lại tài khoản mẫu</button></aside>`:'';
  function login(){
    state.profile=null;$('#student-detail').close();$('#student-detail-content').innerHTML='';$('#contribution-dialog').close();$('#contribution-content').innerHTML='';
    $('#student-main').innerHTML=sampleNote()+`<section class="student-auth"><h1>Đăng nhập hồ sơ võ sinh</h1><p>Dùng mã võ sinh và mật khẩu do CLB cấp để xem thông tin của con.</p><form id="student-login" class="student-form"><div id="login-error" role="alert"></div><label>Mã võ sinh<input name="username" autocomplete="username" maxlength="80" autocapitalize="characters" spellcheck="false" placeholder="Nhập mã võ sinh" required></label>${field('password','Mật khẩu','current-password')}<button class="primary-link" type="submit">Đăng nhập</button><small>Lần đăng nhập đầu tiên cần đổi mật khẩu trước khi mở hồ sơ.</small></form>${sampleHelp()}</section>`;
    $('#student-login').addEventListener('submit',async event=>{
      event.preventDefault();const button=$('button[type=submit]',event.target);button.disabled=true;$('#login-error').textContent='';
      try{const data=Object.fromEntries(new FormData(event.target));apply(await api('/api/student/login','POST',data));await route();}
      catch(error){const box=$('#login-error');if(box){box.className='student-inline-error';box.textContent=error.message;}else failure(error);}
      finally{button.disabled=false;}
    });
  }
  function passwordForm(required){
    $('#student-main').innerHTML=sampleNote()+`<section class="student-auth">${required?'<span class="password-required">Đăng nhập thành công · Cần đổi mật khẩu</span>':''}<h1>${required?'Đổi mật khẩu lần đầu':'Đổi mật khẩu'}</h1><p>${required?'Đặt mật khẩu riêng để tiếp tục mở hồ sơ. Đây là bước bắt buộc trước khi xem thông tin của con.':'Nhập mật khẩu hiện tại và đặt mật khẩu riêng mới.'}</p><p class="student-meta">Mã đăng nhập: <strong>${esc(state.session.username)}</strong></p><form id="student-password" class="student-form"><div id="password-error" role="alert"></div>${field('current_password','Mật khẩu hiện tại','current-password')}${field('password','Mật khẩu mới','new-password')}${field('confirm_password','Nhập lại mật khẩu mới','new-password')}<small>Từ 12 đến 256 ký tự; khác mật khẩu cũ và mã đăng nhập.</small><button class="primary-link" type="submit">Đổi mật khẩu và mở hồ sơ</button></form><div class="student-actions">${required?'': '<button class="secondary" data-profile type="button">Hủy</button>'}<button class="secondary" data-logout type="button">Đăng xuất</button>${demo?'<button class="secondary" data-reset-sample type="button">Đặt lại mẫu</button>':''}</div></section>`;
    $('#student-password').addEventListener('submit',async event=>{
      event.preventDefault();const button=$('button[type=submit]',event.target);button.disabled=true;
      try{const data=Object.fromEntries(new FormData(event.target));if(data.password!==data.confirm_password)throw new Error('Mật khẩu mới và nhập lại chưa khớp.');apply(await api('/api/password','POST',data));state.message=demo?'Đã đổi mật khẩu mẫu trên thiết bị này.':'Đã đổi mật khẩu. Các phiên đăng nhập cũ đã được thu hồi.';await route();}
      catch(error){const box=$('#password-error');if(box){box.className='student-inline-error';box.textContent=error.message;}else failure(error);}
      finally{button.disabled=false;}
    });
  }
  const selectOptions=(items,label)=>`<option value="">${label}</option>${items.map(x=>`<option value="${esc(typeof x==='object'?x.id:x)}">${esc(typeof x==='object'?x.name:x)}</option>`).join('')}`;
  async function profile(id=state.session.athlete_ids[0]){
    if(!id){$('#student-main').innerHTML=sampleNote()+'<div class="student-empty">Tài khoản chưa được gán hồ sơ. Vui lòng liên hệ CLB.<div class="student-actions"><button type="button" class="secondary" data-logout>Đăng xuất</button></div></div>';return;}
    const data=await api('/api/student/athletes/'+encodeURIComponent(id));state.profile=data;
    const a=data.athlete,years=[...new Set(data.achievements.map(r=>r.year))].sort((a,b)=>b-a),tournaments=[...new Map(data.achievements.map(r=>[r.tournament_id,{id:r.tournament_id,name:r.tournament_name}])).values()];
    $('#student-main').innerHTML=sampleNote()+`<div class="student-toolbar"><span>Đã đăng nhập: <strong>${esc(state.session.username)}</strong></span><div><button class="secondary" data-password type="button">Đổi mật khẩu</button><button class="secondary" data-logout type="button">Đăng xuất</button></div></div>${state.message?`<div class="student-toast" role="status">${esc(state.message)}</div>`:''}${state.session.athlete_ids.length>1?`<label class="student-selector">Hồ sơ được cấp quyền<select id="student-selector">${state.session.athlete_ids.map(i=>`<option value="${esc(i)}" ${i===id?'selected':''}>${esc(i)}</option>`).join('')}</select></label>`:''}<section class="profile-heading"><div><div class="eyebrow">${demo?'HỒ SƠ MẪU':'HỒ SƠ ĐƯỢC CẤP QUYỀN'}</div><h1>${esc(a.full_name)}</h1><div class="profile-code">${esc(a.official_code||'Chưa cập nhật')}${demo?'<span class="sample-badge">Dữ liệu kiểm thử</span>':''}</div></div></section><dl class="student-info">${[['Mã võ sinh',a.official_code],['Cơ sở hiện tại',a.branch_name],['Trạng thái học tập',a.status],['Ngày sinh',a.date_of_birth],['Năm sinh',a.birth_year],['Đội đại diện',a.representative_team]].map(([label,value])=>`<div><dt>${label}</dt><dd>${esc(value||'Chưa cập nhật')}</dd></div>`).join('')}</dl><section class="profile-overview"><div><h2>Huy chương</h2><p>${demo?'Số liệu mẫu để thử chức năng.':'Chỉ tính kết quả đã xác minh và được phép hiển thị cho tài khoản.'}</p></div><div class="medal-cards">${[['HCV','Huy chương vàng'],['HCB','Huy chương bạc'],['HCĐ','Huy chương đồng']].map(([key,label])=>`<div class="medal-card ${key}"><strong>${Number(data.medals[key])||0}</strong><span>${label}</span></div>`).join('')}</div><div class="tournament-count"><strong>${Number(data.tournament_count)||0}</strong><span>giải đấu ${demo?'mẫu':''}</span></div></section><section class="history-section"><div class="section-heading"><h2>Lịch sử thi đấu</h2><span>${data.achievements.length} kết quả ${demo?'mẫu':'được phép hiển thị'}</span></div><div class="history-filters"><label>Năm<select id="student-year">${selectOptions(years,'Tất cả năm')}</select></label><label>Giải đấu<select id="student-tournament">${selectOptions(tournaments,'Tất cả giải')}</select></label><label>Huy chương<select id="student-medal">${selectOptions(['HCV','HCB','HCĐ'],'Tất cả huy chương')}</select></label><label>Hình thức<select id="student-type">${selectOptions(['Cá nhân','Đôi','Đồng đội'],'Tất cả hình thức')}</select></label></div><div id="student-history"></div></section>`;
    $('#student-main').insertAdjacentHTML('beforeend','<section class="attendance-section"><div class="section-heading"><h2>Điểm danh tập luyện</h2></div><p class="small-note">Chỉ thống kê buổi đã được Admin/HLV ghi nhận; chưa nhập không được tính là vắng.</p><div id="student-attendance"></div></section>');attendance(data.attendance);
    $('#student-main').insertAdjacentHTML('beforeend',window.TKDContributions.cta());window.TKDContributions.mount(a);
    state.message='';$('.history-filters').addEventListener('change',history);$('#student-selector')?.addEventListener('change',async e=>{try{await profile(e.target.value);}catch(error){failure(error);}});history();
  }
  function attendance(data={items:[],summary:{},total:0,page:1,pages:1}){
    const labels={present:'Có mặt',excused_absent:'Vắng có phép',unexcused_absent:'Vắng không phép'};
    $('#student-attendance').innerHTML='<div class="attendance-totals">'+Object.entries(labels).map(([k,v])=>'<div><strong>'+Number(data.summary[k]||0)+'</strong><span>'+v+'</span></div>').join('')+'</div>'+
      (data.items.length?'<div class="attendance-list">'+data.items.map(r=>'<article><div><strong>'+esc(r.session_date)+' · '+esc(r.start_time)+'</strong><p>'+esc(r.class_name)+' · '+esc(r.branch_name_snapshot||'Chưa cập nhật cơ sở')+'</p></div><span class="attendance-status '+esc(r.status)+'">'+labels[r.status]+'</span>'+(r.note?'<p class="attendance-note">'+esc(r.note)+'</p>':'')+'</article>').join('')+'</div>':'<div class="student-empty">Chưa có dữ liệu điểm danh. CLB sẽ cập nhật sau buổi học.</div>')+
      (data.pages>1?'<div class="student-actions"><button class="secondary" data-attendance-page="'+(data.page-1)+'" '+(data.page<=1?'disabled':'')+'>Trước</button><span>Trang '+data.page+'/'+data.pages+'</span><button class="secondary" data-attendance-page="'+(data.page+1)+'" '+(data.page>=data.pages?'disabled':'')+'>Sau</button></div>':'');
  }
  function history(){
    const rows=state.profile.achievements.filter(r=>(!$('#student-year').value||String(r.year)===$('#student-year').value)&&(!$('#student-tournament').value||r.tournament_id===$('#student-tournament').value)&&(!$('#student-medal').value||r.medal_type===$('#student-medal').value)&&(!$('#student-type').value||r.participation_type===$('#student-type').value));
    $('#student-history').innerHTML=rows.length?rows.map(r=>`<article class="result-card"><span class="medal-tag ${esc(r.medal_type)}">${esc(r.medal_type)}</span><div class="result-copy"><div class="result-tournament">${esc(r.year)} · ${esc(r.tournament_name)}</div><h3>${esc(r.event_name)}</h3><div class="result-tags">${esc(r.discipline)} · ${esc(r.participation_type)}</div></div><button class="result-open" type="button" data-student-result="${esc(r.id)}">Xem chi tiết →</button></article>`).join(''):'<div class="student-empty">Chưa có thành tích phù hợp. Kết quả sẽ hiển thị sau khi CLB xác minh và cấp quyền xem.</div>';
  }
  function link(value){try{const u=new URL(value);return ['http:','https:'].includes(u.protocol)&&!u.username&&!u.password?esc(u.href):'';}catch{return '';}}
  async function detail(id){
    const box=$('#student-detail-content'),dialog=$('#student-detail');box.innerHTML='<p>Đang mở kết quả…</p>';dialog.showModal();
    try{const r=await api('/api/student/achievements/'+encodeURIComponent(id));box.innerHTML=`<div class="eyebrow">${demo?'KẾT QUẢ MẪU':'THÀNH TÍCH ĐÃ XÁC MINH'}</div><h2 id="student-detail-title">${esc(r.event_name)}</h2><dl>${[['Giải đấu',r.tournament_name],['Năm',r.year],['Huy chương',r.medal_type],['Nội dung',r.discipline],['Hình thức',r.participation_type]].map(([k,v])=>`<dt>${k}</dt><dd>${esc(v||'Chưa cập nhật')}</dd>`).join('')}</dl><h3>Minh chứng được phép xem</h3>${link(r.evidence_url)?`<a class="student-proof" href="${link(r.evidence_url)}" target="_blank" rel="noopener noreferrer">Mở liên kết minh chứng ↗</a>`:''}${(r.evidence_files||[]).map(f=>`<a class="student-proof" href="/api/evidence/${encodeURIComponent(f.id)}" target="_blank" rel="noopener noreferrer">Mở tài liệu minh chứng ↗</a>`).join('')}${!r.evidence_url&&!(r.evidence_files||[]).length?'<p class="small-note">Chưa có minh chứng được phép hiển thị.</p>':''}`;}
    catch(error){box.innerHTML=`<h2 id="student-detail-title">Chưa thể mở kết quả</h2><p class="student-inline-error">${esc(error.message)}</p>`;}
  }
  async function route(){
    if(!state.session)return login();
    if(state.session.role!=='viewer'){$('#student-main').innerHTML='<div class="student-empty">Tài khoản này thuộc khu quản trị.<div class="student-actions"><a class="primary-link" href="/admin/">Mở khu quản trị</a><button type="button" class="secondary" data-logout>Đăng xuất</button></div></div>';return;}
    if(state.session.must_change_password)return passwordForm(true);
    await profile();
  }
  function failure(error){if(error.status===401){state.session=null;state.csrf='';login();return;}$('#student-main').innerHTML=sampleNote()+`<div class="student-empty"><p role="alert">${esc(error.message)}</p><div class="student-actions"><button class="secondary" data-retry type="button">Tải lại</button><button class="secondary" data-logout type="button">Đăng xuất</button>${demo?'<button class="secondary" data-reset-sample type="button">Đặt lại mẫu</button>':''}</div></div>`;}
  window.TKDContributions.configure({send:payload=>api('/api/student/submissions','POST',payload)});
  async function start(){try{apply(await api('/api/session'));await route();}catch(error){failure(error);}}
  document.addEventListener('click',async event=>{
    const button=event.target.closest('button');if(!button||button.disabled)return;
    try{
      if(button.hasAttribute('data-fill-sample')&&demo){$('#student-login input[name=username]').value=window.TKDStudentDemo.USER;$('#student-login input[name=password]').value=window.TKDStudentDemo.PASSWORD;}
      if(button.hasAttribute('data-reset-sample')&&demo){adapter.reset();state.session=null;state.csrf='';await start();}
      if(button.hasAttribute('data-logout')){await api('/api/logout','POST',{});state.session=null;state.csrf='';login();}
      if(button.hasAttribute('data-password'))passwordForm(false);
      if(button.hasAttribute('data-profile'))await profile();
      if(button.hasAttribute('data-retry'))await start();
      if(button.dataset.attendancePage)attendance(await api('/api/athletes/'+encodeURIComponent(state.profile.athlete.id)+'/attendance?page='+button.dataset.attendancePage+'&limit=10'));
      if(button.dataset.studentResult)await detail(button.dataset.studentResult);
      if(button.hasAttribute('data-close-detail'))$('#student-detail').close();
    }catch(error){failure(error);}
  });
  if(demo)window.addEventListener('storage',event=>{if(event.key===window.TKDStudentDemo.KEYS.account)start();});
  start();
})();
