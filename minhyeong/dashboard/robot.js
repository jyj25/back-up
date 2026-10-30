// 데이터 층: 로봇 조종 서버(jeongmin/robot/server) API 를 0.7초마다 읽어 화면용 state 를 만든다.
// 주소 뒤에 ?robot=http://localhost:8000 을 붙이면 그 로봇 서버(실제 또는 ROBOT_MODE=fake)에 붙고,
// 없으면 같은 API 모양으로 답하는 브라우저 안 가짜 로봇(Fake)으로 돈다.
const Sortbot = (() => {
  const LABELS = { recycle: '재활용', general: '일반쓰레기', vinyl: '비닐' };   // stations.json 이름과 같게
  const MARKERS = { home: 0, recycle: 1, general: 2, vinyl: 3 };
  const CLASSES = Object.keys(LABELS);
  const STAGES = [['judge', 'AI 판정'], ['find', '통 찾기'], ['arrived', '도착'], ['dump', '쏟기'], ['return', '복귀'], ['done', '완료']];
  const POLL = 700;
  const settings = { capacity: 10 };            // 통 가득 참 기준 (가정, 팀 결정 전)
  const base = (new URLSearchParams(location.search).get('robot') || '').replace(/\/$/, '');

  const state = {
    source: base ? 'live' : 'demo', base,
    connected: false, admin: false,
    robot: null,                                 // GET /api/status 그대로
    mission: null,                               // GET /api/mission 그대로
    stage: null,                                 // STAGES 키 또는 failed / cancelled
    seen: [], frameAt: null,
    lastResult: null,                            // {cls, conf, t} — 임무가 시작될 때의 AI 판정
    bins: { recycle: 0, general: 0, vinyl: 0 }, today: 0,
    log: [], alerts: [],
    stats: { byClass: { recycle: 0, general: 0, vinyl: 0 }, hourly: [2, 4, 1, 0, 0, 3, 6, 5, 8, 4, 7, 0], done: 0, failed: 0, webN: 0, timeSum: 0, confSum: 0, confN: 0 },
    settings,
  };

  const subs = [];
  const emit = () => subs.forEach(f => f(state));
  const isFull = c => state.bins[c] >= settings.capacity;
  let seq = 0;

  function alert(level, title, msg) {            // level: danger | warn | info
    const old = state.alerts.find(a => !a.ack && a.title === title);
    if (old) state.alerts.splice(state.alerts.indexOf(old), 1);
    state.alerts.unshift({ id: ++seq, t: new Date(), level, title, msg, ack: false });
    state.alerts.length = Math.min(state.alerts.length, 40);
  }

  // ── 통신: 진짜 로봇 서버 또는 가짜 로봇 ──
  async function call(method, path, body) {
    if (!base) return Fake.call(method, path, body);
    const r = await fetch(base + path, {
      method, signal: AbortSignal.timeout(2500),
      headers: body ? { 'Content-Type': 'application/json' } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw Object.assign(new Error(typeof data.detail === 'string' ? data.detail : `HTTP ${r.status}`), { status: r.status });
    return data;
  }

  // ── 상태 읽기 ──
  let busy = false, cur = null, webSent = false;
  async function poll() {
    if (busy) return;
    busy = true;
    try {
      // /api/markers 는 로봇이 매번 영상 분석을 하므로 부르지 않고, 임무 중 보이는 마커(seen)만 쓴다
      const [st, ms] = await Promise.all([call('GET', '/api/status'), call('GET', '/api/mission')]);
      setConn(true);
      if (st.blocked && !state.robot?.blocked) alert('warn', '장애물 때문에 멈춤', `앞 ${st.obstacle_cm}cm 안에 물체가 있어 로봇이 섰습니다. 앞쪽 이동은 막히고 뒤·옆·회전만 됩니다.`);
      if (st.camera === 'none' && state.robot?.camera !== 'none') alert('warn', '로봇 카메라 없음', '로봇 서버가 카메라를 찾지 못했습니다. 마커를 볼 수 없어 통 찾아가기가 실패합니다. 케이블과 CAMERA 설정을 확인하세요.');
      state.robot = st;
      state.seen = ms.seen || [];
      state.frameAt = new Date();
      onMission(ms);
    } catch {
      setConn(false);
    }
    busy = false;
    emit();
  }

  function setConn(v) {
    if (state.connected === v) return;
    state.connected = v;
    if (!v) alert('warn', '로봇 서버 연결 끊김', base
      ? `${base} 에 연결할 수 없습니다. 같은 핫스팟인지, 로봇 서버가 켜져 있는지, CORS_ORIGINS 에 이 주소(${location.origin})가 있는지 확인하세요. 임무는 로봇 안에서 계속됩니다.`
      : '가짜 로봇과 연결이 끊겼습니다 (시뮬레이션).');
  }

  function stageOf(ms) {
    const p = ms.phase, home = ms.target === 'home' && ms.station !== 'home';
    if (p === 'idle') return null;
    if (p === 'starting') return 'judge';
    if (['search', 'align', 'approach'].includes(p)) return home ? 'return' : 'find';
    if (p === 'arrived') return home ? 'return' : 'arrived';
    if (p === 'dumping' || p === 'backing') return 'dump';
    return p;                                    // done | failed | cancelled
  }

  function onMission(ms) {
    state.mission = ms;
    state.stage = stageOf(ms);
    if (ms.running && !cur && ms.station in LABELS) {          // 새 임무 시작 = AI 판정이 나온 것
      cur = { id: ++seq, t: new Date(), cls: ms.station, conf: ms.conf ?? null, by: webSent ? 'web' : 'ai', img: null };
      webSent = false;
      if (cur.by === 'ai') state.lastResult = { cls: cur.cls, conf: cur.conf, t: cur.t };
    }
    // '도착'은 0.7초 사이에 지나갈 수 있어서 쏟는 중에도 아직 안 찍었으면 찍는다
    if (cur && !cur.shot && (state.stage === 'arrived' || state.stage === 'dump')) { cur.shot = true; snapshot(cur); }
    if (cur && !ms.running && ['done', 'failed', 'cancelled'].includes(ms.phase)) finish(cur, ms);
  }

  async function snapshot(rec) {                 // 도착했을 때 로봇 카메라 사진 = 어느 통에 갔는지 증거
    if (!base) { rec.img = 'demo'; return; }
    try {
      const r = await fetch(base + '/api/camera.jpg', { signal: AbortSignal.timeout(2500) });
      if (r.ok) rec.img = URL.createObjectURL(await r.blob());
    } catch { /* 사진이 없어도 기록은 남긴다 */ }
  }

  function finish(rec, ms) {
    cur = null;
    Object.assign(rec, { result: ms.phase, ms: Date.now() - rec.t, steps: ms.steps, message: ms.message });
    state.log.unshift(rec);
    state.log.length = Math.min(state.log.length, 200);
    const st = state.stats, c = rec.cls;
    if (ms.phase === 'done') {
      state.bins[c]++; state.today++; st.byClass[c]++; st.hourly[st.hourly.length - 1]++;
      st.done++; st.timeSum += rec.ms;
      if (rec.by === 'web') st.webN++;
      if (rec.conf != null) { st.confSum += rec.conf; st.confN++; }
      if (isFull(c)) alert('warn', `${LABELS[c]} 통 가득 참`, `${LABELS[c]} 통이 ${settings.capacity}개가 됐습니다. 통을 비운 뒤 ‘비웠어요’를 누르세요.`);
    } else if (ms.phase === 'failed') {
      st.failed++;
      alert('danger', '임무 실패', `${LABELS[c]} 통: ${ms.message || '이유 없음'}. 로봇을 출발점에 다시 두고 시작하세요.`);
    } else {
      alert('info', '임무 취소', `${LABELS[c]} 통 임무를 취소했습니다 (${ms.message || '취소'}).`);
    }
  }

  // ── 명령 (로봇 서버가 다시 검사한다: 이미 임무 중이면 409, 앞이 막히면 이동 거절) ──
  function interlocks(cls) {
    const r = state.robot, m = state.mission;
    const list = [
      ['로봇 서버 연결', state.connected],
      ['임무 중 아님', !m?.running],
      ['앞 장애물 없음', !r?.blocked],
    ];
    if (cls && cls !== 'home') list.push([`${LABELS[cls]} 통 여유`, !isFull(cls)]);
    return list.map(([label, ok]) => ({ label, ok }));
  }

  async function send(station) {
    const fails = interlocks(station).filter(x => !x.ok);
    if (fails.length) return { ok: false, reason: `${fails.map(f => f.label).join(', ')} 조건이 맞지 않아 보내지 않았습니다.` };
    try {
      const ms = await call('POST', '/api/mission', { station, dump: station !== 'home', return_home: station !== 'home' });
      webSent = true;                            // 응답을 받은 그 자리에서 기록을 시작해야 '웹에서 보냄'이 섞이지 않는다
      onMission({ ...ms, running: true, seen: [] });
      emit();
      return { ok: true, reason: station === 'home' ? '출발점으로 돌아갑니다.' : `${LABELS[station]} 통으로 보냈습니다.` };
    } catch (e) {
      return { ok: false, reason: e.status === 409 ? '로봇이 이미 임무 중입니다. 먼저 임무를 취소하세요.' : `보내지 못했습니다: ${e.message}` };
    }
  }

  async function stop(kind) {                    // kind: 'stop' = 정지(임무 취소 + 바퀴 정지) | 'cancel' = 임무만 취소
    try {
      await call('POST', kind === 'stop' ? '/api/stop' : '/api/mission/cancel');
      if (kind === 'stop') alert('danger', '정지', '웹에서 정지를 보냈습니다. 진행 중이던 임무는 취소됩니다.');
      poll();
      return { ok: true, reason: kind === 'stop' ? '정지했습니다. 진행 중이던 임무는 취소됩니다.' : '임무를 취소했습니다.' };
    } catch (e) {
      return { ok: false, reason: `웹에서 정지 명령이 전달되지 않습니다 (${e.message}). 로봇 본체의 전원 스위치를 끄세요.` };
    }
  }

  function setSetting(key, raw) {
    if (!state.admin) return { ok: false, reason: '관리자 모드에서만 바꿀 수 있습니다.' };
    const v = Number(raw);
    if (key !== 'capacity' || !Number.isInteger(v) || v < 1 || v > 50) return { ok: false, reason: '1~50 사이 정수만 쓸 수 있습니다. 저장하지 않았습니다.' };
    settings.capacity = v; emit();
    return { ok: true, reason: '저장했습니다.' };
  }

  // ── 가짜 로봇: 로봇 서버와 같은 모양으로 답한다 (navigator.py 의 phase 순서) ──
  const Fake = (() => {
    let mission = { phase: 'idle', station: null, target: null, message: '', steps: 0 };
    let running = false, plan = [], blocked = false, idle = 0;
    const sim = { down: false, failNext: null, auto: true };
    const err = (status, msg) => Object.assign(new Error(msg), { status });
    const rep = (p, n) => Array(n).fill(p);
    const go = name => [...rep('search', 2 + Math.floor(Math.random() * 3)), ...rep('align', 2), ...rep('approach', 3 + Math.floor(Math.random() * 3)), 'arrived'].map(p => [p, name]);

    function start(station, conf) {
      if (running) throw err(409, '이미 임무 중입니다. 먼저 /api/mission/cancel');
      running = true; blocked = false;
      mission = { phase: 'starting', station, target: station, message: '', steps: 0, conf };   // conf: 로봇 서버에 요청할 필드
      plan = station === 'home' ? go('home') : [...go(station), ['dumping', station], ['backing', station], ...go('home')];
      plan.push(['done', 'home']);
    }
    function end(phase, message) { running = false; mission.phase = phase; mission.message = message; }

    setInterval(() => {
      if (!running) {
        // 실제로는 라즈베리파이가 ESP32 의 "RESULT recycle 0.93" 한 줄을 받으면 임무를 시작한다
        if (sim.auto && ++idle > 6 && Math.random() < 0.3) { idle = 0; if (Math.random() < 0.8) start(CLASSES[Math.floor(Math.random() * 3)], +(0.8 + Math.random() * 0.19).toFixed(2)); }
        return;
      }
      const [phase, target] = plan.shift();
      mission.steps++;
      if (sim.failNext && phase === 'approach' && target !== 'home') {
        const why = sim.failNext; sim.failNext = null;
        if (why === 'blocked') { blocked = true; return end('failed', '앞에 장애물이 있어 멈췄습니다'); }
        return end('failed', `${LABELS[mission.station]} 마커 ${MARKERS[mission.station]} 번을 못 찾았습니다`);
      }
      mission.target = target;
      mission.phase = phase;
      mission.message = phase === 'done' ? '완료' : phase === 'dumping' ? `${LABELS[target]} 에 쏟는 중` : `${target === 'home' ? '출발점 (물건 싣는 곳)' : LABELS[target]} (마커 ${MARKERS[target]})`;
      if (phase === 'done') running = false;
    }, POLL);

    function seen() {
      if (!running || !['align', 'approach', 'arrived'].includes(mission.phase)) return [];
      const left = plan.filter(([p]) => p === 'approach').length;
      return [{ id: MARKERS[mission.target], cx: mission.phase === 'align' ? 0.35 - Math.random() * 0.1 : (Math.random() - 0.5) * 0.12, size: mission.phase === 'arrived' ? 0.32 : Math.max(0.08, 0.28 - left * 0.04) }];
    }

    async function call(method, path, body) {
      if (sim.down) throw err(0, '연결 끊김');
      const moving = running && !['starting', 'arrived', 'dumping', 'done'].includes(mission.phase);
      const key = method + ' ' + path;
      if (key === 'GET /api/status') return { mode: 'fake', moving: moving ? 'forward' : null, speed: moving ? 70 : 0, pan: 90, tilt: 30, led: null, camera: 'sim', max_speed: 150, blocked, obstacle_cm: 15, mission: mission.phase };
      if (key === 'GET /api/mission') return { ...mission, running, seen: seen() };
      if (key === 'POST /api/mission') { start(body.station, null); return mission; }
      if (key === 'POST /api/mission/cancel') { if (running) end('cancelled', '취소'); return { ...mission, running }; }
      if (key === 'POST /api/stop') { if (running) end('cancelled', '정지 버튼'); return {}; }
      throw err(404, 'Not Found');
    }
    return { call, sim };
  })();

  // ── 그림: 가짜 로봇 카메라(앞쪽) 장면과 마커 박스 (viewBox 100×75) ──
  function scene(seen, { bg = true, obj = true, box = true } = {}) {
    let out = bg ? '<rect width="100" height="75" fill="#57524f"/><rect y="48" width="100" height="27" fill="#3d3937"/>' : '';
    for (const m of seen || []) {
      const w = m.size * 100, x = 50 + m.cx * 50 - w / 2, y = 38 - w / 2;
      const name = Object.keys(MARKERS).find(k => MARKERS[k] === m.id);
      if (obj) out += `<rect x="${x - w * 0.6}" y="${y - w * 0.4}" width="${w * 2.2}" height="${w * 2.2}" fill="#8a6a4f"/><rect x="${x}" y="${y}" width="${w}" height="${w}" fill="#f4f1ec"/><rect x="${x + w * .15}" y="${y + w * .15}" width="${w * .7}" height="${w * .7}" fill="#1c1918"/><rect x="${x + w * .3}" y="${y + w * .3}" width="${w * .2}" height="${w * .2}" fill="#f4f1ec"/>`;
      if (box) {
        const label = `마커 ${m.id} ${name === 'home' ? '출발점' : LABELS[name] || ''}`;
        out += `<rect x="${x}" y="${y}" width="${w}" height="${w}" fill="none" stroke="#e0895f" stroke-width=".8"/>`
          + `<rect x="${x}" y="${y - 5}" width="${label.length * 2.9 + 3}" height="5" fill="#e0895f"/>`
          + `<text x="${x + 1.5}" y="${y - 1.3}" font-size="3.6" font-weight="700" fill="#1c1918" font-family="Pretendard,sans-serif">${label}</text>`;
      }
    }
    return out;
  }

  const pct = conf => conf == null ? '—' : Math.round(conf * 100) + '%';
  const fmtTime = (d, ms) => !d ? '—' : d.toTimeString().slice(0, 8) + (ms ? '.' + String(d.getMilliseconds()).padStart(3, '0') : '');
  const secs = ms => ms == null ? '—' : (ms / 1000).toFixed(1) + '초';
  const RESULT = { done: '완료', failed: '실패', cancelled: '취소' };

  function csv() {
    const rows = state.log.map(r => [r.t.toISOString(), LABELS[r.cls], r.by === 'web' ? '웹' : 'AI', RESULT[r.result], r.conf ?? '', (r.ms / 1000).toFixed(1), r.steps, `"${(r.message || '').replace(/"/g, '""')}"`].join(','));
    return '﻿시각,통,보낸 쪽,결과,확신도,걸린 시간(초),걸음,메시지\n' + rows.join('\n');
  }

  setInterval(poll, POLL);
  poll();

  return {
    LABELS, MARKERS, CLASSES, STAGES, RESULT, state, settings,
    on: f => subs.push(f),
    isFull, interlocks, send, stop, setSetting, scene, pct, fmtTime, secs, csv,
    empty: c => { state.bins[c] = 0; emit(); },
    ack: id => { const a = state.alerts.find(a => a.id === id); if (a) a.ack = true; emit(); },
    ackAll: () => { state.alerts.forEach(a => a.ack = true); emit(); },
    setAdmin: v => { state.admin = v; emit(); },
    sim: base ? null : {
      down: v => { Fake.sim.down = v; },
      failNext: why => { Fake.sim.failNext = why; },
      auto: v => { Fake.sim.auto = v; },
    },
  };
})();
