'use strict';
(() => {
  const $ = (s, root = document) => root.querySelector(s);
  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const num = v => new Intl.NumberFormat('vi-VN').format(Number(v) || 0);
  const initials = name => String(name).trim().split(/\s+/).slice(-2).map(w => w[0]).join('').toUpperCase();
  const medalNames = {'HCV':'Huy chương vàng','HCB':'Huy chương bạc','HCĐ':'Huy chương đồng'};
  const icons = {search:'M21 21l-5-5 M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0',arrow:'M5 12h14 M14 7l5 5-5 5',shield:'M12 3l8 3v6c0 5-8 9-8 9s-8-4-8-9V6z M8 12l3 3 5-6',medal:'M8 3l4 7 4-7 M18 16a6 6 0 1 1-12 0 6 6 0 0 1 12 0 M12 13v6',book:'M3 3h7l2 2 2-2h7v17h-7l-2 1-2-1H3z M12 5v16',trophy:'M8 3h8v6a4 4 0 0 1-8 0z M8 5H4v3a4 4 0 0 0 4 4 M16 5h4v3a4 4 0 0 1-4 4 M12 13v5 M8 21h8 M9 18h6',file:'M14 2H6v20h12V8z M14 2v6h6 M8 13h7 M8 17h5'};
  const icon = name => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${icons[name] || icons.book}"/></svg>`;
  const medal = m => `<span class="medal-tag ${esc(m)}">${icon('medal')}${esc(m)}</span>`;
  const medalCards = counts => `<div class="medal-cards">${Object.entries(medalNames).map(([key,label]) => `<div class="medal-card ${esc(key)}">${icon('medal')}<strong>${num(counts?.[key])}</strong><span>${label}</span></div>`).join('')}</div>`;
  const empty = (title, copy) => `<div class="empty-state">${icon('book')}<h3>${esc(title)}</h3><p>${esc(copy)}</p></div>`;
  const errorBox = error => `<div class="error" role="alert">${esc(error.message || error)}</div>`;
  const options = (items, label) => `<option value="">${esc(label)}</option>${items.map(v => `<option value="${esc(typeof v === 'object' ? v.id : v)}">${esc(typeof v === 'object' ? v.name : v)}</option>`).join('')}`;
  const state = {profile:null, results:[], token:0};
  const demo = document.body.dataset.preview === 'sample';
  const sampleTag = '<span class="sample-badge">Dữ liệu kiểm thử</span>';

  async function api(path) {
    let response;
    try { response = await fetch(path, {credentials:'omit', cache:'no-store', headers:{Accept:'application/json'}}); }
    catch { throw new Error('Chưa thể kết nối sổ thành tích. Vui lòng thử lại sau.'); }
    let data;
    try { data = await response.json(); } catch { throw new Error('Chưa thể tải dữ liệu. Vui lòng thử lại sau.'); }
    if (!response.ok) { const error = new Error(data.error || 'Chưa thể tải dữ liệu.'); error.status = response.status; throw error; }
    return data;
  }

  function landing() {
    state.profile = null;
    const q = new URLSearchParams(location.search).get('q') || '';
    $('#noi-dung').innerHTML = `<div class="content lookup-content"><section id="tra-cuu" class="lookup-section" aria-labelledby="lookup-title"><div class="lookup-heading"><h1 id="lookup-title">Tra cứu thông tin võ sinh</h1><p>Nhập tên hoặc mã võ sinh để xem hồ sơ và lịch sử thành tích thi đấu.</p></div><form id="search-form" class="search-form" role="search"><label class="search-label" for="athlete-search">Tên hoặc mã võ sinh</label><div class="search-input">${icon('search')}<input id="athlete-search" name="q" type="search" autocomplete="off" minlength="2" maxlength="100" placeholder="Nhập tên hoặc mã võ sinh…" value="${esc(q)}" aria-describedby="search-help" required><button type="submit">Tìm kiếm</button></div><p id="search-help">Có thể nhập tên không dấu. Nếu trùng tên, hãy kiểm tra mã võ sinh trước khi mở hồ sơ.</p></form><div id="search-results" aria-live="polite"></div></section></div>`;
    $('#search-results').innerHTML = '<div class="search-hint">Nhập ít nhất 2 ký tự để tìm võ sinh. Chỉ hồ sơ được phép công bố mới hiển thị.</div>';
    $('.lookup-section').insertAdjacentHTML('afterend', window.TKDContributions.cta());
    window.TKDContributions.mount();
    if (demo) {
      $('#search-form').insertAdjacentHTML('afterend', '<div class="sample-shortcuts"><strong>Hồ sơ mẫu:</strong><button type="button" data-sample-search="MAU-TKD-001">Võ sinh mẫu 01</button><button type="button" data-sample-search="MAU-TKD-002">Võ sinh mẫu 02</button><button type="button" data-sample-search="MAU-TKD-003">Võ sinh mẫu 03</button></div>');
      $('#search-results').innerHTML = '<div class="search-hint">Chọn hồ sơ mẫu ở trên hoặc tìm “vo sinh mau” để kiểm tra chức năng.</div>';
    }
    $('#search-form').addEventListener('submit', event => { event.preventDefault(); search(1); });
    if (q) search(Number(new URLSearchParams(location.search).get('page')) || 1, false);
  }

  async function search(page, updateUrl = true) {
    const q = $('#athlete-search').value.trim();
    if (q.length < 2) { $('#search-results').innerHTML = errorBox('Vui lòng nhập ít nhất 2 ký tự.'); return; }
    const token = ++state.token;
    const button = $('#search-form button'); button.disabled = true;
    $('#search-results').innerHTML = '<div class="loading" role="status">Đang tìm sổ thành tích…</div>';
    if (updateUrl) history.pushState({}, '', '/?' + new URLSearchParams({q, page}) + '#tra-cuu');
    try {
      const data = await api('/api/public/athletes?' + new URLSearchParams({q, page, limit:12}));
      if (token !== state.token) return;
      state.results = data.items;
      $('#search-results').innerHTML = data.items.length ? `<div class="results-heading"><h2>Kết quả tìm kiếm</h2><span>${num(data.total)} hồ sơ</span></div><div class="athlete-grid">${data.items.map(a => `<a class="athlete-card" href="/ho-so/${encodeURIComponent(a.id)}"><span class="athlete-avatar">${esc(initials(a.full_name))}</span><div class="athlete-info"><h3>${esc(a.full_name)}</h3><div class="athlete-code">${esc(a.official_code)} ${demo ? sampleTag : `<span class="verified-icon" title="Danh tính đã xác thực">${icon('shield')}Đã xác thực</span>`}</div></div><div class="athlete-summary"><div class="mini-medals">${Object.keys(medalNames).map(m => `<span>${medal(m)}<b>${num(a.medals[m])}</b></span>`).join('')}</div><small>${num(a.tournament_count)} ${demo ? 'giải kiểm thử' : 'giải đấu được công bố'}</small></div><span class="athlete-open" aria-label="Mở hồ sơ">${icon('arrow')}</span></a>`).join('')}</div><div class="pagination"><span>Trang ${num(data.page)} / ${num(data.pages)}</span><div><button data-page="${data.page - 1}" ${data.page <= 1 ? 'disabled' : ''}>← Trước</button><button data-page="${data.page + 1}" ${data.page >= data.pages ? 'disabled' : ''}>Sau →</button></div></div>` : empty('Chưa tìm thấy hồ sơ được công bố', 'Kiểm tra lại tên hoặc mã võ sinh. Hồ sơ chưa được công bố sẽ không xuất hiện trong kết quả tìm kiếm.');
      if (demo) {
        const count = $('.results-heading>span'); if (count) count.textContent = num(data.total) + ' hồ sơ mẫu';
        if (!data.items.length) $('#search-results').innerHTML = empty('Chưa tìm thấy hồ sơ mẫu', 'Thử “Võ sinh mẫu 01”, “vo sinh mau” hoặc “MAU-TKD-001”. Dữ liệu thật chưa công bố không được đưa vào bản thử.');
      }
    } catch (error) { if (token === state.token) $('#search-results').innerHTML = errorBox(error) + '<button class="secondary" data-retry-search>Thử lại</button>'; }
    finally { if (token === state.token) button.disabled = false; }
  }

  function renderProfile(profile) {
    state.profile = profile;
    const a = profile.athlete;
    const years = [...new Set(profile.achievements.map(r => r.year))].sort((a,b) => b-a);
    const tournaments = [...new Map(profile.achievements.map(r => [r.tournament_id, {id:r.tournament_id,name:r.tournament_name}])).values()];
    $('#noi-dung').innerHTML = `<div class="content profile-content">
      <a class="back-link" href="/">← Trở về tìm kiếm</a>
      <section class="profile-heading"><div class="profile-avatar">${esc(initials(a.full_name))}</div><div><div class="eyebrow">HỒ SƠ VÕ SINH</div><h1>${esc(a.full_name)}</h1><div class="profile-code">${esc(a.official_code)} <span>${icon('shield')}Danh tính đã xác thực</span></div></div><button class="secondary share-button" data-share>Sao chép liên kết ↗</button></section>
      <div id="share-status" role="status" class="share-status"></div>
      <section class="profile-overview"><div><h2>Huy chương</h2><p>Chỉ tính thành tích đã xác minh và được phép công bố.</p></div>${medalCards(profile.medals)}<div class="tournament-count"><strong>${num(profile.tournament_count)}</strong><span>giải đấu<br>được công bố</span></div></section>
      <section class="history-section"><div class="section-heading"><h2>Lịch sử thi đấu</h2><span>${num(profile.achievement_count)} thành tích được công bố</span></div><div class="history-filters"><label>Năm thi đấu<select id="filter-year">${options(years, 'Tất cả các năm')}</select></label><label>Giải đấu<select id="filter-tournament">${options(tournaments, 'Tất cả giải đấu')}</select></label><label>Huy chương<select id="filter-medal">${options(Object.keys(medalNames).map(m => ({id:m,name:medalNames[m]})), 'Tất cả huy chương')}</select></label><label>Hình thức<select id="filter-type">${options(['Cá nhân','Đôi','Đồng đội'], 'Tất cả hình thức')}</select></label></div><div id="history"></div></section></div>`;
    $('.history-filters').addEventListener('change', renderHistory);
    $('.history-section').insertAdjacentHTML('afterend', window.TKDContributions.cta());
    window.TKDContributions.mount(a);
    if (demo) {
      $('.profile-heading .eyebrow').textContent = 'HỒ SƠ KIỂM THỬ';
      $('.profile-code>span').outerHTML = sampleTag;
      $('.profile-overview>div>p').textContent = 'Huy chương minh họa để thử chức năng, không phải thành tích thật của CLB.';
      $('.tournament-count>span').textContent = 'giải kiểm thử';
      $('.history-section .section-heading>span').textContent = num(profile.achievement_count) + ' thành tích mẫu';
    }
    renderHistory();
  }

  function renderHistory() {
    const results = state.profile.achievements.filter(r => (!$('#filter-year').value || String(r.year) === $('#filter-year').value) && (!$('#filter-tournament').value || r.tournament_id === $('#filter-tournament').value) && (!$('#filter-medal').value || r.medal_type === $('#filter-medal').value) && (!$('#filter-type').value || r.participation_type === $('#filter-type').value));
    if (!results.length) { $('#history').innerHTML = empty('Chưa có thành tích trong mục này', state.profile.achievements.length ? 'Thử thay đổi bộ lọc để xem các kết quả khác.' : 'Thành tích sẽ xuất hiện khi được xác minh và công bố.'); return; }
    let year;
    $('#history').innerHTML = `<div class="timeline">${results.map(r => { const heading = year !== r.year ? `<h3 class="timeline-year">${esc(r.year)}</h3>` : ''; year = r.year; return `${heading}<article class="result-card"><div class="result-medal ${esc(r.medal_type)}">${icon('medal')}</div><div class="result-copy"><div class="result-tournament">${esc(r.tournament_name)}</div><h3>${esc(r.event_name)}</h3><div class="result-tags">${medal(r.medal_type)}<span>${esc(r.discipline)}</span><span>${esc(r.participation_type)}</span></div></div><button class="result-open" data-result="${esc(r.id)}" aria-label="Xem chi tiết ${esc(r.event_name)}">Xem chi tiết ${icon('arrow')}</button></article>`; }).join('')}</div>`;
  }

  function safeLink(value) {
    try { const u = new URL(value); return ['https:', 'http:'].includes(u.protocol) && !u.username && !u.password ? esc(u.href) : ''; }
    catch { return ''; }
  }

  async function detail(id) {
    const dialog = $('#achievement-dialog');
    $('#dialog-content').innerHTML = '<div class="loading">Đang mở thành tích…</div>';
    if (!dialog.open) dialog.showModal();
    try {
      const r = await api('/api/public/achievements/' + encodeURIComponent(id));
      const fields = [['Giải đấu',r.tournament_name],['Năm thi đấu',r.year],['Nội dung',r.event_name],['Nhóm nội dung',r.discipline],['Hình thức',r.participation_type],['Lứa tuổi',r.age_category],['Hạng cân',r.weight_category],['Cấp đai',r.belt_category]];
      const links = (r.evidence_files || []).map(f => `<a class="evidence-link" href="/api/public/evidence/${encodeURIComponent(f.id)}" target="_blank" rel="noopener noreferrer">${icon('file')}Minh chứng ${f.mime_type === 'application/pdf' ? 'PDF' : 'hình ảnh'} ↗</a>`);
      if (safeLink(r.evidence_url)) links.unshift(`<a class="evidence-link" href="${safeLink(r.evidence_url)}" target="_blank" rel="noopener noreferrer">${icon('file')}Mở minh chứng được công bố ↗</a>`);
      $('#dialog-content').innerHTML = `<div class="eyebrow">THÀNH TÍCH ĐÃ XÁC MINH</div>${medal(r.medal_type)}<h2 id="dialog-title">${esc(r.event_name)}</h2><dl>${fields.map(([label,value]) => `<dt>${label}</dt><dd>${esc(value || 'Chưa cập nhật')}</dd>`).join('')}</dl><h3>${r.participation_type === 'Cá nhân' ? 'Võ sinh' : 'Thành viên được công bố'}</h3><div class="members">${r.athletes.map(a => `<a href="/ho-so/${encodeURIComponent(a.id)}">${esc(a.full_name)}<small>${esc(a.official_code)}</small></a>`).join('')}</div>${r.participation_type !== 'Cá nhân' ? '<p class="small-note">Chỉ hiển thị thành viên đã cho phép công bố hồ sơ.</p>' : ''}<h3>Minh chứng</h3>${links.join('') || '<p class="small-note">Chưa có minh chứng được phép công bố cho khách.</p>'}`;
      if (demo) $('#dialog-content>.eyebrow').textContent = 'THÀNH TÍCH KIỂM THỬ · KHÔNG PHẢI KẾT QUẢ THẬT';
    } catch (error) { $('#dialog-content').innerHTML = '<h2 id="dialog-title">Chưa thể mở thành tích</h2>' + errorBox(error); }
  }

  async function start() {
    ++state.token;
    if (location.pathname === '/' && /^#(dashboard|athletes|tournaments|achievements|queue|import|portal|audit|users|settings)(\/|$)/.test(location.hash)) { location.replace('/admin/' + location.hash); return; }
    try {
      if (location.pathname.startsWith('/ho-so/')) {
        const id = decodeURIComponent(location.pathname.split('/')[2] || '');
        renderProfile(await api('/api/public/athletes/' + encodeURIComponent(id)));
      } else { landing(); }
    } catch (error) { $('#noi-dung').innerHTML = `<div class="content failure"><h1>${error.status === 404 ? 'Hồ sơ chưa được công bố' : 'Chưa thể mở sổ thành tích'}</h1>${errorBox(error)}<a class="primary-link" href="/">Trở về trang tra cứu ${icon('arrow')}</a></div>`; }
  }

  document.addEventListener('click', async event => {
    const page = event.target.closest('[data-page]'); if (page && !page.disabled) search(Number(page.dataset.page));
    const result = event.target.closest('[data-result]'); if (result) detail(result.dataset.result);
    if (event.target.closest('[data-close]')) $('#achievement-dialog').close();
    if (event.target.closest('[data-retry-search]')) search(1);
    const shortcut = event.target.closest('[data-sample-search]');
    if (shortcut) { $('#athlete-search').value = shortcut.dataset.sampleSearch; await search(1); $('#search-results').scrollIntoView({behavior:'smooth', block:'start'}); }
    if (event.target.closest('[data-share]')) {
      try { await navigator.clipboard.writeText(location.origin + location.pathname); $('#share-status').textContent = 'Đã sao chép liên kết hồ sơ.'; }
      catch { $('#share-status').textContent = 'Liên kết hồ sơ: ' + location.origin + location.pathname; }
    }
  });
  $('#achievement-dialog').addEventListener('click', event => { if (event.target === event.currentTarget) { const r = event.currentTarget.getBoundingClientRect(); if (event.clientX < r.left || event.clientX > r.right || event.clientY < r.top || event.clientY > r.bottom) event.currentTarget.close(); } });
  window.addEventListener('popstate', start);
  start();
})();
