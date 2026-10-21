'use strict';
const attendanceLabels={present:'Có mặt',excused_absent:'Vắng có phép',unexcused_absent:'Vắng không phép'};
async function renderAttendance(id){
  const athletes=await allAthletes();state.attendanceAthlete=id||'';
  const d=await api('/api/attendance?'+qs(id?{athlete_id:id}:{}));state.last=d;
  return pageTitle('Điểm danh tập luyện','Admin/HLV ghi nhận từng buổi đã học. Chưa nhập không được tính là vắng.',btn('Nhập điểm danh','new-attendance','plus','primary'))+
    '<div class="toolbar"><div class="filters">'+(!id?filterSelect('athlete_id',athletes.map(a=>({id:a.id,name:a.full_name+' · '+(a.official_code||a.legacy_athlete_id||'Chưa có mã')})),'Tất cả võ sinh'):'<a class="btn" href="#attendance">Tất cả võ sinh</a>')+filterSelect('status',Object.entries(attendanceLabels).map(([id,name])=>({id,name})),'Tất cả trạng thái')+
    '<label>Từ ngày <input type="date" data-filter="from_date" value="'+html(state.filters.from_date||'')+'"></label><label>Đến ngày <input type="date" data-filter="to_date" value="'+html(state.filters.to_date||'')+'"></label></div></div>'+
    card('Thống kê trong bộ lọc','<div class="card-body"><div class="stat-grid">'+Object.entries(attendanceLabels).map(([key,label])=>stat(d.summary[key],label,'Chỉ tính buổi đã nhập','calendar')).join('')+'</div></div>')+
    card('Lịch sử điểm danh',d.items.length?'<div class="table-wrap"><table class="data-table"><thead><tr><th>Võ sinh</th><th>Buổi học</th><th>Cơ sở / lớp</th><th>Trạng thái</th><th>Ghi chú cho gia đình</th><th></th></tr></thead><tbody>'+d.items.map(r=>'<tr><td><a href="#athletes/'+html(r.athlete_id)+'">'+html(r.full_name)+'</a><span class="cell-sub">'+text(r.official_code)+'</span></td><td>'+html(r.session_date)+'<span class="cell-sub">'+html(r.start_time)+'</span></td><td>'+text(r.branch_name_snapshot)+'<span class="cell-sub">'+html(r.class_name)+'</span></td><td>'+attendanceLabels[r.status]+'</td><td class="cell-wrap">'+text(r.note)+'</td><td>'+btn('Sửa','edit-attendance','edit','tiny',r.id)+'</td></tr>').join('')+'</tbody></table></div>'+pagination(d):empty('Chưa có điểm danh','Nhập từng buổi; không suy luận buổi vắng từ dữ liệu còn thiếu.','calendar'))+footer();
}
async function editAttendance(id){
  const athletes=await allAthletes(),r=id?await api('/api/attendance/'+encodeURIComponent(id)):{};
  const selected=r.athlete_id||state.attendanceAthlete||state.filters.athlete_id||'';
  openForm(id?'Sửa điểm danh':'Nhập điểm danh',
    selectField('athlete_id','Võ sinh',athletes.map(a=>({id:a.id,name:a.full_name+' · '+(a.official_code||a.legacy_athlete_id||'Chưa có mã')})),selected,{required:true,full:true})+
    inputField('session_date','Ngày học',r.session_date,{type:'date',required:true})+
    inputField('start_time','Giờ bắt đầu',r.start_time,{type:'time',required:true})+
    inputField('class_name','Tên lớp / nhóm học',r.class_name,{required:true})+
    selectField('branch_id','Cơ sở tại buổi học',state.branches,r.branch_id,{placeholder:'Chưa cập nhật'})+
    selectField('status','Kết quả điểm danh',Object.entries(attendanceLabels).map(([id,name])=>({id,name})),r.status,{required:true})+
    textareaField('note','Ghi chú cho gia đình (hiển thị trong hồ sơ)',r.note),
    async f=>api('/api/attendance'+(id?'/'+encodeURIComponent(id):''),{method:id?'PATCH':'POST',body:{...formObject(f),...(id?{version:r.version}:{})}}),
    {notice:notice('Chỉ nhập dữ liệu đã kiểm tra. Ngày, giờ và lớp xác định một buổi; không nhập trùng. Cơ sở của buổi học được giữ khi võ sinh chuyển cơ sở.','info'),success:'Đã lưu điểm danh.'});
  if(id){
    const footer=$('#modal .form-actions');
    if(footer){const b=document.createElement('button');b.type='button';b.className='btn';b.textContent='Lưu trữ bản ghi sai';footer.append(b);b.addEventListener('click',async()=>{try{await api('/api/attendance/'+encodeURIComponent(id),{method:'DELETE',body:{version:r.version}});closeModal();await navigate();toast('Đã lưu trữ bản ghi sai và giữ lịch sử chỉnh sửa.');}catch(e){toast(e.message,true);}});}
  }
}
