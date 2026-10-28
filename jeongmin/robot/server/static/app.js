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

async function poll() {
  try {
    const s = await api('GET', '/api/status');
    $('mode').textContent = s.mode === 'real' ? '실제 로봇' : '가짜 모드';
    $('mode').className = `badge ${s.mode}`;
    $('moving').textContent = s.blocked ? '장애물 정지' : (s.moving ?? '정지');
    if (s.camera !== 'none' && !$('cam').src) { $('cam').src = '/api/stream'; $('cam-msg').hidden = true; }
    $('dist').textContent = (await api('GET', '/api/distance')).cm;
    $('line').textContent = (await api('GET', '/api/line')).sensors.map((x) => (x ? '●' : '○')).join('');
  } catch {
    $('mode').textContent = '연결 끊김';
    $('mode').className = 'badge';
  }
}
poll();
setInterval(poll, 500);
