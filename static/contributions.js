(function (root) {
  'use strict';
  const medals = ['HCV', 'HCB', 'HCĐ', 'Chưa xác định'];
  const disciplines = ['Quyền', 'Đối kháng', 'Công phá', 'Biểu diễn', 'Khác', 'Chưa xác định'];
  const types = ['Cá nhân', 'Đôi', 'Đồng đội', 'Chưa xác định'];
  const storageKey = 'tkd.preview.submissions.v1';
  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

  function validate(data) {
    for (const [key, max] of Object.entries({athlete_name:120, athlete_code:80, public_athlete_id:80, tournament_name:240, event_name:300, evidence_url:2000, notes:2000, contact:160})) {
      if (typeof data[key] !== 'string' || data[key].length > max) throw new Error('Một trường dữ liệu quá dài hoặc không hợp lệ.');
    }
    if (!data.athlete_name.trim() || !data.tournament_name.trim() || !data.event_name.trim()) throw new Error('Cần họ tên võ sinh, tên giải và nội dung thi đấu.');
    if (!Number.isInteger(data.year) || data.year < 1900 || data.year > new Date().getFullYear() + 1) throw new Error('Vui lòng kiểm tra năm thi đấu.');
    if (!medals.includes(data.medal_type) || !disciplines.includes(data.discipline) || !types.includes(data.participation_type)) throw new Error('Vui lòng chọn nội dung, hình thức và huy chương.');
    if (data.evidence_url) {
      let url;
      try { url = new URL(data.evidence_url); } catch { throw new Error('Liên kết minh chứng không hợp lệ.'); }
      if (!['https:', 'http:'].includes(url.protocol) || url.username || url.password) throw new Error('Minh chứng cần liên kết http hoặc https hợp lệ.');
    }
    if (data.consent_to_review !== true) throw new Error('Cần đồng ý gửi thông tin để CLB đối chiếu.');
    if (data.website) throw new Error('Không thể tiếp nhận đề nghị này.');
    return data;
  }

  function demoRows(storage) {
    const raw = storage.getItem(storageKey);
    if (!raw) return [];
    let rows;
    try { rows = JSON.parse(raw); } catch { throw new Error('Dữ liệu thử trên thiết bị bị lỗi. Hãy xóa dữ liệu thử để bắt đầu lại.'); }
    if (!Array.isArray(rows)) throw new Error('Dữ liệu thử trên thiết bị không hợp lệ.');
    return rows;
  }

  function saveDemo(storage, payload) {
    validate(payload);
    const number = /^MAU-TKD-00([1-3])$/.exec(payload.athlete_code)?.[1];
    if (!number || payload.athlete_name !== 'Võ sinh mẫu 0' + number) throw new Error('Bản thử chỉ nhận đề nghị cho hồ sơ mẫu.');
    const rows = demoRows(storage);
    const data = {...payload, contact:''};
    const existing = rows.find(r => r.data.client_request_id === data.client_request_id);
    if (existing) {
      if (JSON.stringify(existing.data) !== JSON.stringify(data)) throw new Error('Mã gửi đã dùng cho đề nghị khác. Hãy mở biểu mẫu mới.');
      return {receipt_id:existing.id, status:'sample_saved', duplicate:true};
    }
    if (rows.length >= 20) throw new Error('Đã lưu 20 đề nghị mẫu trên thiết bị. Hãy xóa dữ liệu thử để tiếp tục.');
    const row = {id:'MAU-' + payload.client_request_id, created_at:new Date().toISOString(), status:'pending', data};
    storage.setItem(storageKey, JSON.stringify([row, ...rows]));
    return {receipt_id:row.id, status:'sample_saved', duplicate:false};
  }

  if (typeof module !== 'undefined' && module.exports) module.exports = {validate, demoRows, saveDemo, storageKey};
  if (!root.document) return;
  const $ = (selector, parent = document) => parent.querySelector(selector);
  const isDemo = document.body.dataset.preview === 'sample';
  const isStatic = document.body.dataset.staticPreview === '1';
  let context = null, pending = null, transport = null;
  const choose = items => items.map(item => `<option value="${esc(item)}">${esc(item)}</option>`).join('');
  const demoDefault = {id:'sample-athlete-1', full_name:'Võ sinh mẫu 01', official_code:'MAU-TKD-001', is_sample:true};

  function cta() {
    if (isStatic && !isDemo) return '<section class="contribution-section" id="bo-sung"><div><h2>Bổ sung thành tích</h2><p>Bản xem thử này chưa kết nối máy chủ tiếp nhận. Chức năng gửi sẽ mở khi CLB triển khai backend.</p></div></section>';
    return `<section class="contribution-section" id="bo-sung"><div><h2>Bổ sung thành tích</h2><p>Thiếu kết quả thi đấu? Gửi thông tin và minh chứng để CLB đối chiếu.</p><small>${isDemo ? 'Bản thử chỉ lưu đề nghị mẫu trên trình duyệt, chưa gửi tới CLB.' : 'Đề nghị cần được CLB kiểm tra trước khi ghi nhận.'}</small></div><button class="secondary" type="button" data-contribute>${isDemo ? 'Thử bổ sung thành tích' : 'Bổ sung thành tích'} <span aria-hidden="true">＋</span></button></section><div id="contribution-history" aria-live="polite"></div>`;
  }

  function mount(athlete = null) {
    context = athlete;
    const box = $('#contribution-history');
    if (!box || !isDemo) return;
    try {
      const rows = demoRows(localStorage).filter(r => !athlete || r.data.athlete_code === athlete.official_code);
      box.innerHTML = rows.length ? `<section class="sample-requests"><div class="results-heading"><h3>Đề nghị mẫu đã lưu trên thiết bị này</h3><button class="secondary" type="button" data-clear-samples>Xóa dữ liệu thử</button></div><p>Chưa gửi tới CLB. Các đề nghị này không được cộng vào huy chương và không xuất hiện trên thiết bị khác.</p>${rows.map(r => `<article><span class="sample-badge">Mẫu · Chờ đối chiếu</span><h4>${esc(r.data.event_name)} · ${esc(r.data.medal_type)}</h4><p>${esc(r.data.athlete_name)} · ${esc(r.data.tournament_name)} · ${esc(r.data.year)}</p><small>Mã đề nghị: ${esc(r.id)}</small></article>`).join('')}</section>` : '';
    } catch (error) { box.innerHTML = `<p class="error">${esc(error.message)} <button type="button" class="secondary" data-clear-samples>Xóa dữ liệu thử</button></p>`; }
  }

  function field(name, label, {value='', type='text', required=false, max=240, full=false, readonly=false, help=''} = {}) {
    return `<label class="contribution-field ${full ? 'full' : ''}"><span>${esc(label)}${required ? ' *' : ''}</span><input name="${name}" type="${type}" value="${esc(value)}" ${required ? 'required' : ''} maxlength="${max}" ${readonly ? 'readonly' : ''} ${type === 'number' ? 'min="1900" max="' + (new Date().getFullYear() + 1) + '"' : ''}>${help ? `<small>${esc(help)}</small>` : ''}</label>`;
  }
  const select = (name, label, items) => `<label class="contribution-field"><span>${label}</span><select name="${name}">${choose(items)}</select></label>`;

  function open(athlete = context) {
    if (isStatic && !isDemo) return;
    const a = athlete || (isDemo ? demoDefault : null);
    const dialog = $('#contribution-dialog');
    pending = null;
    $('#contribution-content').innerHTML = `<div class="eyebrow">${isDemo ? 'THỬ BIỂU MẪU · DỮ LIỆU MẪU' : 'GỬI CLB ĐỐI CHIẾU'}</div><h2 id="contribution-title">Bổ sung thành tích</h2><p class="contribution-intro">${isDemo ? 'Chỉ dùng thông tin mẫu. Đề nghị được lưu trên trình duyệt để thử thao tác, chưa gửi tới CLB.' : 'Mỗi đề nghị tương ứng một kết quả thi đấu. Đề nghị gắn với hồ sơ được cấp quyền cho tài khoản này.'}</p><form id="contribution-form"><div id="contribution-error" role="alert"></div><div class="contribution-grid">${field('athlete_name','Họ tên võ sinh',{value:a?.full_name, required:true, max:120, readonly:true})}${field('athlete_code','Mã võ sinh (nếu có)',{value:a?.official_code, max:80, readonly:true, help:'Hồ sơ được gán cho tài khoản đăng nhập.'})}${field('tournament_name','Tên giải đấu',{required:true, full:true})}${field('year','Năm thi đấu',{type:'number', required:true, max:4})}${select('medal_type','Huy chương', ['Chưa xác định', 'HCV', 'HCB', 'HCĐ'])}${field('event_name','Nội dung thi đấu',{required:true, max:300, full:true})}${select('discipline','Nhóm nội dung', ['Chưa xác định', ...disciplines.slice(0,-1)])}${select('participation_type','Hình thức', ['Chưa xác định', ...types.slice(0,-1)])}${field('evidence_url','Liên kết minh chứng (nếu có)',{type:'url', full:true, max:2000, help:'Dán link ảnh, giấy chứng nhận hoặc kết quả giải. Không cần mở quyền công khai; CLB sẽ kiểm tra quyền truy cập.'})}<label class="contribution-field full"><span>Ghi chú bổ sung</span><textarea name="notes" maxlength="2000" rows="3" placeholder="Ví dụ: cần bổ sung thành viên đồng đội, chưa rõ tên nội dung…"></textarea></label>${isDemo ? '' : field('contact','Email hoặc số điện thoại liên hệ (không bắt buộc)',{max:160, full:true, help:'Chỉ quản trị viên xem để liên hệ làm rõ đề nghị.'})}<label class="form-trap" aria-hidden="true">Website<input name="website" type="text" tabindex="-1" autocomplete="off"></label></div><label class="contribution-consent"><input type="checkbox" name="consent_to_review" required><span>${isDemo ? 'Tôi hiểu đây là đề nghị mẫu, chỉ lưu trên trình duyệt và chưa gửi tới CLB.' : 'Tôi đồng ý gửi thông tin này cho CLB để đối chiếu và có quyền cung cấp các tài liệu liên quan. Gửi đề nghị không đồng nghĩa với công bố hồ sơ hoặc xác minh thành tích.'}</span></label><div class="contribution-actions"><button type="button" class="secondary" data-close-contribution>Hủy</button><button type="submit" class="primary-link">Kiểm tra đề nghị →</button></div></form><div id="contribution-review" hidden></div>`;
    $('#contribution-form').addEventListener('submit', event => {
      event.preventDefault();
      const data = Object.fromEntries(new FormData(event.target));
      data.year = Number(data.year); data.consent_to_review = data.consent_to_review === 'on';
      data.public_athlete_id = a?.id || ''; data.contact = data.contact || '';
      data.client_request_id = crypto.randomUUID();
      for (const key of Object.keys(data)) if (typeof data[key] === 'string') data[key] = data[key].trim();
      try { validate(data); pending = data; review(); } catch (error) { $('#contribution-error').textContent = error.message; }
    });
    if (!dialog.open) dialog.showModal();
  }

  function review() {
    $('#contribution-form').hidden = true;
    const labels = {athlete_name:'Võ sinh', athlete_code:'Mã võ sinh', tournament_name:'Giải đấu', year:'Năm', event_name:'Nội dung', discipline:'Nhóm nội dung', participation_type:'Hình thức', medal_type:'Huy chương', evidence_url:'Minh chứng', notes:'Ghi chú', contact:'Liên hệ riêng'};
    const box = $('#contribution-review'); box.hidden = false;
    box.innerHTML = `<h3>Kiểm tra trước khi ${isDemo ? 'lưu mẫu' : 'gửi'}</h3><dl>${Object.entries(labels).filter(([key]) => !isDemo || key !== 'contact').map(([key,label]) => `<dt>${label}</dt><dd>${esc(pending[key] || 'Chưa cung cấp')}</dd>`).join('')}</dl><p class="small-note">${isDemo ? 'Đề nghị thử chỉ lưu trên trình duyệt. Huy chương mẫu đang hiển thị sẽ giữ nguyên.' : 'Đề nghị sẽ chờ CLB xác minh. Tên hoặc mã được cung cấp chưa phải căn cứ xác thực người nhận.'}</p><div id="submission-status" role="alert"></div><div class="contribution-actions"><button type="button" class="secondary" data-edit-contribution>Chỉnh sửa</button><button type="button" class="primary-link" data-send-contribution>${isDemo ? 'Lưu đề nghị mẫu' : 'Gửi CLB đối chiếu'} →</button></div>`;
  }

  async function send(button) {
    if (!pending) return;
    button.disabled = true;
    $('[data-edit-contribution]').disabled = true;
    try {
      let result;
      if (isDemo) result = saveDemo(localStorage, pending);
      else {
        if(!transport)throw new Error('Vui lòng đăng nhập trước khi gửi đề nghị.');
        result=await transport(pending);
      }
      $('#contribution-review').innerHTML = `<div class="submission-success" role="status"><span class="${isDemo ? 'sample-badge' : 'received-badge'}">${isDemo ? 'Đề nghị mẫu · Chờ đối chiếu' : 'Đã tiếp nhận · Chờ đối chiếu'}</span><h3>${isDemo ? 'Đã lưu đề nghị mẫu trên trình duyệt' : 'Đã gửi đề nghị bổ sung'}</h3><p>${isDemo ? 'Chưa gửi tới CLB. Bạn có thể đóng, tải lại trang và xem đề nghị mẫu đã lưu trên thiết bị này.' : 'CLB sẽ kiểm tra thông tin và minh chứng. Thành tích chưa được xác minh hoặc cộng vào huy chương.'}</p><small>Mã đề nghị: ${esc(result.receipt_id)}</small><button type="button" class="primary-link" data-close-contribution>Hoàn tất</button></div>`;
      pending = null; mount(context);
    } catch (error) {
      $('#submission-status').textContent = error.name === 'AbortError' || error instanceof TypeError ? 'Chưa nhận được xác nhận. Kiểm tra kết nối và thử gửi lại; mã gửi được giữ nguyên để tránh trùng.' : error.message;
      button.disabled = false; $('[data-edit-contribution]').disabled = false;
    }
  }

  document.addEventListener('click', event => {
    if (event.target.closest('[data-contribute]')) open();
    if (event.target.closest('[data-close-contribution]')) $('#contribution-dialog').close();
    if (event.target.closest('[data-edit-contribution]')) { $('#contribution-review').hidden = true; $('#contribution-form').hidden = false; }
    const sendButton = event.target.closest('[data-send-contribution]'); if (sendButton && !sendButton.disabled) send(sendButton);
    if (event.target.closest('[data-clear-samples]')) {
      try { localStorage.removeItem(storageKey); mount(context); } catch { $('#contribution-history').textContent = 'Trình duyệt chưa cho phép xóa dữ liệu thử.'; }
    }
  });
  root.TKDContributions = {cta, mount, open, configure:options=>{transport=options.send;}};
})(typeof window !== 'undefined' ? window : globalThis);
