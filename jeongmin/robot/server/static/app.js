// 라즈봇 조종 화면. 버튼을 누르고 있는 동안 0.2초마다 같은 이동 명령을 다시 보낸다.
// 서버는 명령마다 0.5초 뒤 자동 정지하므로, 손을 떼거나 연결이 끊기면 로봇이 멈춘다.
const $ = (id) => document.getElementById(id);
const REPEAT_MS = 200;
let current = null;
let timer = null;

async function api(method, path, body) {
  const res = await fetch(path, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error(`${path} ${res.status}`);
  return res.json();
}

function send(action) {
  api('POST', '/api/move', { action, speed: Number($('speed').value), duration_ms: 500 }).catch(() => {});
}

function start(action, button) {
  if (current === action) return;
  stop();
  current = action;
  button?.classList.add('active');
  send(action);
  timer = setInterval(() => send(action), REPEAT_MS);
}

function stop() {
  clearInterval(timer);
  timer = null;
  if (current !== null) api('POST', '/api/stop').catch(() => {});
  current = null;
  document.querySelectorAll('.pad .active').forEach((b) => b.classList.remove('active'));
}

for (const b of document.querySelectorAll('[data-move]')) {
  b.addEventListener('pointerdown', (e) => { e.preventDefault(); b.setPointerCapture(e.pointerId); start(b.dataset.move, b); });
  for (const ev of ['pointerup', 'pointercancel', 'lostpointercapture']) b.addEventListener(ev, stop);
}
$('stop').addEventListener('click', () => { stop(); api('POST', '/api/stop'); });

const KEYS = { w: 'forward', s: 'backward', a: 'turn_left', d: 'turn_right', q: 'strafe_left', e: 'strafe_right' };
document.addEventListener('keydown', (e) => {
  if (e.target.closest?.('input, select')) return;
  if (e.code === 'Space') { e.preventDefault(); stop(); api('POST', '/api/stop'); return; }
  const action = KEYS[e.key.toLowerCase()];
  if (action && !e.repeat) start(action, document.querySelector(`[data-move="${action}"]`));
});
document.addEventListener('keyup', (e) => { if (KEYS[e.key.toLowerCase()] === current) stop(); });
window.addEventListener('blur', stop);

$('speed').addEventListener('input', () => { $('speed-v').textContent = $('speed').value; });
for (const id of ['pan', 'tilt']) {
  $(id).addEventListener('input', () => { $(`${id}-v`).textContent = $(id).value; });
  $(id).addEventListener('change', () => api('POST', '/api/servo', { [id]: Number($(id).value) }));
}
$('beep').addEventListener('click', () => api('POST', '/api/beep', { ms: 150 }));
$('led').addEventListener('change', () => api('POST', '/api/led', { color: $('led').value || null }));

// ---- 통 찾아가기 ----
const PHASES = {
  idle: '대기', starting: '시작', look: '둘러보는 중', closer: '멀리 보이는 마커로 다가가는 중', search: '마커 찾는 중', align: '방향 맞추는 중', approach: '다가가는 중',
  arrived: '도착', docking: '옆면 맞추는 중', dumping: '쏟는 중', backing: '뒤로 빠지는 중', done: '완료', failed: '실패', cancelled: '취소됨',
};

async function loadStations() {
  const stations = await api('GET', '/api/stations');
  for (const [name, info] of Object.entries(stations)) {
    const b = document.createElement('button');
    b.textContent = name === 'home' ? '출발점으로' : info.label;
    b.title = `마커 ${info.marker}`;
    b.addEventListener('click', () => {
      stop();
      const home = name === 'home';
      api('POST', '/api/mission', {
        station: name, dump: !home && $('m-dump').checked, return_home: !home && $('m-home').checked,
      }).catch((e) => { $('m-msg').textContent = String(e); });
    });
    $('stations').append(b);
  }
}
$('m-cancel').addEventListener('click', () => api('POST', '/api/mission/cancel'));
$('auto-sort').addEventListener('change', () => api('POST', '/api/sort', { auto: $('auto-sort').checked }));

async function pollSort() {
  const s = await api('GET', '/api/sort');
  if (document.activeElement !== $('auto-sort')) $('auto-sort').checked = s.auto;
  const v = s.last_verdict;
  $('v-last').textContent = !v ? '없음'
    : v.class ? `${v.class} ${Math.round((v.conf ?? 0) * 100)}% → ${v.result}` : `${v.error ? '오류 ' + v.error : '판정 없음'}`;
  const b = s.board;
  $('v-board').textContent = b.want === 'none' ? '사용 안 함' : b.port ? `연결 ${b.port}` : (b.error ?? '찾는 중');
}

async function pollMission() {
  const m = await api('GET', '/api/mission');
  $('m-phase').textContent = PHASES[m.phase] ?? m.phase;
  $('m-msg').textContent = m.message;
  $('m-cancel').disabled = !m.running;
  for (const b of $('stations').children) b.disabled = m.running;
  const seen = m.running ? m.seen : (await api('GET', '/api/markers')).markers;
  $('m-seen').textContent = seen.length ? seen.map((k) => `${k.id}번(${Math.round(k.size * 100)}%)`).join(' ') : '없음';
}

async function poll() {
  try {
    const s = await api('GET', '/api/status');
    $('mode').textContent = s.mode === 'real' ? '실제 로봇' : '가짜 모드';
    $('mode').className = `badge ${s.mode}`;
    $('moving').textContent = s.blocked ? '장애물 정지' : (s.moving ?? '정지');
    if (s.camera !== 'none' && !$('cam').src) { $('cam').src = '/api/stream'; $('cam-msg').hidden = true; }
    $('dist').textContent = (await api('GET', '/api/distance')).cm;
    $('line').textContent = (await api('GET', '/api/line')).sensors.map((x) => (x ? '●' : '○')).join('');
    await pollMission();
    await pollSort();
  } catch {
    $('mode').textContent = '연결 끊김';
    $('mode').className = 'badge';
  }
}
loadStations().catch(() => {});
poll();
setInterval(poll, 500);
