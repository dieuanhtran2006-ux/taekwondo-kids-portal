(function (root) {
  'use strict';
  const fail = (message, status=404) => { const e = new Error(message); e.status = status; throw e; };
  const fold = value => String(value || '').toLocaleLowerCase('vi').replace(/đ/g,'d').normalize('NFKD').replace(/[\u0300-\u036f]/g,'').trim().replace(/\s+/g,' ');
  function read(snapshot, path) {
    const url = new URL(path, 'https://preview.invalid');
    if (url.pathname === '/api/public/summary') return snapshot.summary;
    if (url.pathname === '/api/public/athletes') {
      const q = (url.searchParams.get('q') || '').trim();
      if (q.length > 100) fail('Từ khóa tối đa 100 ký tự.',422);
      const key = fold(q);
      if (key.length < 2) return {items:[],total:0,page:1,pages:1,query_required:true};
      let page = Number(url.searchParams.get('page') || 1), limit = Number(url.searchParams.get('limit') || 12);
      if (!Number.isInteger(page) || !Number.isInteger(limit)) fail('Trang tìm kiếm không hợp lệ.',422);
      limit = Math.max(1,Math.min(24,limit));
      const profiles = snapshot.profiles.filter(p => fold(p.athlete.full_name + ' ' + p.athlete.official_code).includes(key))
        .sort((a,b) => a.athlete.full_name.localeCompare(b.athlete.full_name,'vi') || a.athlete.official_code.localeCompare(b.athlete.official_code));
      const pages = Math.max(1,Math.ceil(profiles.length/limit)); page = Math.max(1,Math.min(page,pages));
      return {items:profiles.slice((page-1)*limit,page*limit).map(p=>({...p.athlete,medals:p.medals,tournament_count:p.tournament_count,achievement_count:p.achievement_count})),total:profiles.length,page,pages,query_required:false};
    }
    const parts = url.pathname.split('/');
    if (parts.length === 5 && parts[1] === 'api' && parts[2] === 'public') {
      const id = decodeURIComponent(parts[4]);
      if (parts[3] === 'athletes') { const p = snapshot.profiles.find(p => p.athlete.id === id); if (p) return p; }
      if (parts[3] === 'achievements') { const r = snapshot.achievements.find(r => r.id === id); if (r) return r; }
    }
    fail('Hồ sơ hoặc thành tích không có trong bản xem thử.');
  }
  if (typeof module !== 'undefined' && module.exports) module.exports = {read,fold};
  root.TKDPreviewData = {read,fold};
})(typeof window !== 'undefined' ? window : globalThis);
