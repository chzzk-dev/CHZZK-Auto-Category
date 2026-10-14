import json
import queue
import threading
import time
import uuid
import re
from collections import deque
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from version import APP_VERSION


class BridgeError(RuntimeError):
    pass


LOG_PAGE = r'''<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>CHZZK Auto Category · Local Log</title>
<style>
:root{color-scheme:dark;--bg:#06140f;--panel:#0a2018;--panel2:#0d2a20;--line:#1f6b4d;--text:#d9f7e8;--muted:#7fba9f;--mint:#20d7a0;--mint2:#12b986;--warn:#ffc857;--err:#ff7b7b}
*{box-sizing:border-box}html,body{margin:0;min-height:100%;background:radial-gradient(circle at 20% 0,#103326 0,transparent 38%),var(--bg);color:var(--text);font-family:Inter,Pretendard,"Noto Sans KR","Malgun Gothic",system-ui,sans-serif}
body{padding:28px}.wrap{max-width:1180px;margin:0 auto}.top{display:flex;gap:16px;align-items:center;justify-content:space-between;margin-bottom:18px}.brand{display:flex;gap:13px;align-items:center}.logo{width:48px;height:48px;border-radius:15px;display:grid;place-items:center;background:linear-gradient(135deg,var(--mint),#1fe6b4);color:#042117;font-size:25px;font-weight:900;box-shadow:0 10px 34px #00d89c22}.title{font-size:21px;font-weight:850;letter-spacing:.2px}.sub{margin-top:3px;color:var(--muted);font-size:13px}.status{display:flex;align-items:center;gap:8px;padding:9px 13px;border:1px solid #235f49;border-radius:999px;background:#092219;color:#b9ead3;font-size:13px}.dot{width:9px;height:9px;border-radius:50%;background:var(--mint);box-shadow:0 0 0 5px #20d7a017}.panel{border:1px solid #1b5e45;border-radius:18px;background:#071b14dd;box-shadow:0 22px 70px #0006;overflow:hidden}.toolbar{display:flex;gap:10px;align-items:center;padding:14px;border-bottom:1px solid #174d39;background:#0a2119}.search{min-width:0;flex:1;background:#0d2b21;border:1px solid #23664c;color:var(--text);border-radius:11px;padding:10px 12px;outline:none}.search:focus{border-color:var(--mint)}button{border:1px solid #276c51;background:#0d2a20;color:#d9f7e8;border-radius:10px;padding:10px 13px;cursor:pointer;font-weight:700}button:hover{background:#123a2b}.primary{background:linear-gradient(90deg,#13bf8c,#20d7a0);border:0;color:#032219}.meta{padding:10px 15px;color:var(--muted);font-size:12px;border-bottom:1px solid #123f2f;display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap}.logs{height:calc(100vh - 235px);min-height:420px;overflow:auto;padding:8px 0 18px;font-family:"Cascadia Code","JetBrains Mono",Consolas,monospace;font-size:13px;line-height:1.6}.row{display:grid;grid-template-columns:86px 72px minmax(0,1fr);gap:12px;padding:6px 16px;border-left:3px solid transparent}.row:hover{background:#0d2c2166}.time{color:#6ca98d}.level{font-size:11px;font-weight:800;letter-spacing:.4px;color:#78dcb2}.message{white-space:pre-wrap;overflow-wrap:anywhere;color:#d9f7e8}.empty{padding:70px 20px;text-align:center;color:#6fa88e}.paused .dot{background:var(--warn);box-shadow:0 0 0 5px #ffc85717}@media(max-width:700px){body{padding:12px}.top{align-items:flex-start;flex-direction:column}.toolbar{flex-wrap:wrap}.search{flex-basis:100%}.logs{height:calc(100vh - 290px)}.row{grid-template-columns:76px minmax(0,1fr)}.level{display:none}}
</style>
</head>
<body>
<div class="wrap">
  <div class="top">
    <div class="brand"><div class="logo">C</div><div><div class="title">CHZZK Auto Category</div><div class="sub">127.0.0.1:5000 · Local Log Viewer</div></div></div>
    <div class="status" id="status"><span class="dot"></span><span id="statusText">실시간 로그 연결 중</span></div>
  </div>
  <section class="panel">
    <div class="toolbar">
      <input id="search" class="search" placeholder="로그 검색…" autocomplete="off">
      <button id="pause">일시정지</button>
      <button id="copy">전체 복사</button>
      <button id="bottom" class="primary">맨 아래</button>
    </div>
    <div class="meta"><span id="count">0개 로그</span><span>1초마다 자동 갱신 · 최근 로그 최대 1,000개</span></div>
    <div class="logs" id="logs"><div class="empty">로그를 불러오는 중입니다…</div></div>
  </section>
</div>
<script>
const logsEl=document.getElementById('logs');
const searchEl=document.getElementById('search');
const countEl=document.getElementById('count');
const statusEl=document.getElementById('status');
const statusText=document.getElementById('statusText');
const pauseBtn=document.getElementById('pause');
let rows=[], paused=false, lastId=0, loading=false;
function render(){
  const q=searchEl.value.trim().toLowerCase();
  const visible=q?rows.filter(x=>(x.message||'').toLowerCase().includes(q)):rows;
  countEl.textContent=`${visible.length}개 로그${q?' · 검색 결과':''}`;
  logsEl.textContent='';
  if(!visible.length){const e=document.createElement('div');e.className='empty';e.textContent=q?'검색 결과가 없습니다.':'아직 기록된 로그가 없습니다.';logsEl.appendChild(e);return;}
  const frag=document.createDocumentFragment();
  for(const x of visible){
    const row=document.createElement('div');row.className='row';
    const t=document.createElement('span');t.className='time';t.textContent=x.time||'';
    const l=document.createElement('span');l.className='level';l.textContent=(x.level||'INFO').toUpperCase();
    const m=document.createElement('span');m.className='message';m.textContent=x.message||'';
    row.append(t,l,m);frag.appendChild(row);
  }
  const nearBottom=logsEl.scrollHeight-logsEl.scrollTop-logsEl.clientHeight<80;
  logsEl.appendChild(frag);
  if(nearBottom&&!paused) logsEl.scrollTop=logsEl.scrollHeight;
}
async function refresh(){
  if(paused||loading)return;loading=true;
  try{
    const r=await fetch(`/log/data?after=${lastId}`,{cache:'no-store'});
    if(!r.ok)throw new Error(`HTTP ${r.status}`);
    const data=await r.json();
    if(Array.isArray(data.logs)&&data.logs.length){rows.push(...data.logs);if(rows.length>1000)rows=rows.slice(-1000);lastId=rows[rows.length-1].id||lastId;render();}
    statusText.textContent='실시간 로그 연결됨';statusEl.classList.remove('paused');
  }catch(e){statusText.textContent='로그 연결 실패 · 재시도 중';statusEl.classList.add('paused');}
  finally{loading=false;}
}
searchEl.addEventListener('input',render);
pauseBtn.addEventListener('click',()=>{paused=!paused;pauseBtn.textContent=paused?'다시 시작':'일시정지';statusEl.classList.toggle('paused',paused);statusText.textContent=paused?'표시 일시정지':'실시간 로그 연결됨';if(!paused)refresh();});
document.getElementById('bottom').addEventListener('click',()=>{logsEl.scrollTop=logsEl.scrollHeight;});
document.getElementById('copy').addEventListener('click',async()=>{const text=rows.map(x=>`${x.time}  [${(x.level||'INFO').toUpperCase()}]  ${x.message}`).join('\n');try{await navigator.clipboard.writeText(text);document.getElementById('copy').textContent='복사됨';setTimeout(()=>document.getElementById('copy').textContent='전체 복사',1200);}catch{}});
refresh();setInterval(refresh,1000);
</script>
</body>
</html>'''


class LocalExtensionBridge:
    def __init__(self, host='127.0.0.1', port=5000, extension_id=''):
        self.host = host
        self.port = int(port)
        self.extension_id = str(extension_id or '').strip()
        self.commands = queue.Queue()
        self.results = {}
        self.condition = threading.Condition()
        self.server = None
        self.thread = None
        self.connected_at = 0.0
        self.extension_info = None
        self.extension_info_at = 0.0
        self.extension_response_at = ''
        self.pending_ids = {}
        self.info_sessions = {}
        self.logs = deque(maxlen=1000)
        self.log_lock = threading.Lock()
        self.log_seq = 0

    @property
    def connected(self):
        return bool(self.connected_at and time.monotonic() - self.connected_at < 40)

    def receive_extension_info(self, payload, origin_id):
        if not isinstance(payload, dict) or payload.get('type') != 'extension_info':
            raise ValueError('잘못된 확장 정보 메시지입니다.')
        extension_id = str(payload.get('extensionId') or '')
        version = str(payload.get('version') or '')
        protocol = payload.get('protocolVersion')
        session = str(payload.get('sessionId') or '')
        sequence = payload.get('sequence', 0)
        if (extension_id != origin_id or not re.fullmatch(r'[a-p]{32}', extension_id)
                or not re.fullmatch(r'\d+\.\d+\.\d+(?:\.\d+)?', version)
                or not isinstance(protocol, int) or isinstance(protocol, bool)
                or not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 0
                or len(session) > 128 or payload.get('connected') is not True):
            raise ValueError('확장 정보의 형식이 올바르지 않습니다.')
        with self.condition:
            if session and sequence <= self.info_sessions.get(session, -1):
                return False
            if session:
                self.info_sessions[session] = sequence
                while len(self.info_sessions) > 32:
                    self.info_sessions.pop(next(iter(self.info_sessions)))
            self.extension_info = {'extensionId': extension_id, 'version': version, 'protocolVersion': protocol,
                                   'browser': str(payload.get('browser') or '확인 불가')[:32]}
            self.extension_info_at = time.monotonic()
            self.extension_response_at = datetime.now().strftime('%H:%M:%S')
        return True

    def extension_status(self):
        with self.condition:
            info = dict(self.extension_info or {})
            fresh = bool(self.connected and self.extension_info_at and time.monotonic() - self.extension_info_at < 70)
            if not self.connected:
                state = '응답 없음' if self.connected_at else '설치 확인 불가'
                return {'state': state, 'version': None, 'compatibility': '확인 불가', 'last_response': self.extension_response_at}
            if not fresh:
                return {'state': '버전 확인 불가', 'version': None, 'compatibility': '확인 불가', 'last_response': self.extension_response_at}
            compatible = info.get('protocolVersion') == 1
            return {**info, 'state': '정상 연결' if compatible else '버전 호환 불가',
                    'compatibility': '정상' if compatible else '프로토콜 불일치', 'last_response': self.extension_response_at}

    def accept_result(self, payload):
        command_id = str(payload.get('id') or '')
        with self.condition:
            deadline = self.pending_ids.get(command_id)
            if deadline is None or deadline < time.monotonic():
                return False
            if command_id in self.results:
                return False
            self.results[command_id] = payload
            self.condition.notify_all()
        return True

    def add_log(self, message, level='info'):
        text = str(message or '').strip()
        if not text:
            return
        with self.log_lock:
            self.log_seq += 1
            self.logs.append({
                'id': self.log_seq,
                'time': datetime.now().strftime('%H:%M:%S'),
                'level': str(level or 'info').lower(),
                'message': text,
            })

    def get_logs(self, after=0):
        try:
            after = max(0, int(after))
        except (TypeError, ValueError):
            after = 0
        with self.log_lock:
            return [dict(item) for item in self.logs if int(item.get('id', 0)) > after]

    def _origin_allowed(self, origin):
        if not origin or not origin.startswith('chrome-extension://'):
            return False
        if not self.extension_id:
            return True
        return origin == f'chrome-extension://{self.extension_id}'

    def start(self):
        if self.server:
            return

        bridge = self

        class Handler(BaseHTTPRequestHandler):
            server_version = 'ChzzkLocalBridge/1.1'

            def log_message(self, _format, *_args):
                return

            def _cors(self):
                origin = self.headers.get('Origin', '')
                if bridge._origin_allowed(origin):
                    self.send_header('Access-Control-Allow-Origin', origin)
                    self.send_header('Vary', 'Origin')
                self.send_header('Access-Control-Allow-Headers', 'Content-Type, X-Extension-Id')
                self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
                if self.headers.get('Access-Control-Request-Private-Network') == 'true':
                    self.send_header('Access-Control-Allow-Private-Network', 'true')
                self.send_header('Cache-Control', 'no-store')

            def _json(self, status, payload):
                data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
                self.send_response(status)
                self._cors()
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _html(self, status, content):
                data = content.encode('utf-8')
                self.send_response(status)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', str(len(data)))
                self.send_header('Cache-Control', 'no-store')
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.send_header('Referrer-Policy', 'no-referrer')
                self.end_headers()
                self.wfile.write(data)

            def _authorized(self):
                origin = self.headers.get('Origin', '')
                claimed_id = self.headers.get('X-Extension-Id', '').strip().lower()
                if not bridge._origin_allowed(origin):
                    return False
                if claimed_id:
                    prefix = 'chrome-extension://'
                    origin_id = origin[len(prefix):].strip().lower() if origin.startswith(prefix) else ''
                    if claimed_id != origin_id:
                        return False
                return True

            def _mark_extension_connected(self):
                was_connected = bridge.connected
                bridge.connected_at = time.monotonic()
                bridge.extension_response_at = datetime.now().strftime('%H:%M:%S')
                if not was_connected:
                    bridge.add_log('Chrome 확장프로그램 연결됨 · 로컬 브리지 통신 시작')

            def do_OPTIONS(self):
                if not self._authorized():
                    self.send_response(403)
                    self._cors()
                    self.end_headers()
                    return
                self.send_response(204)
                self._cors()
                self.end_headers()

            def do_GET(self):
                parsed = urlparse(self.path)
                path = parsed.path

                # The log viewer is intentionally available to the local browser only.
                # The HTTP server itself is bound to 127.0.0.1, so it is not exposed
                # to other machines on the network.
                if path in ('/log', '/log/'):
                    self._html(200, LOG_PAGE)
                    return

                if path == '/log/data':
                    query = parse_qs(parsed.query)
                    after = (query.get('after') or ['0'])[0]
                    self._json(200, {
                        'ok': True,
                        'version': APP_VERSION,
                        'logs': bridge.get_logs(after),
                    })
                    return

                if not self._authorized():
                    self._json(403, {'ok': False, 'error': 'Chrome 확장프로그램 요청만 허용됩니다.'})
                    return

                self._mark_extension_connected()

                if path == '/health':
                    self._json(200, {
                        'ok': True,
                        'app': 'ChzzkAutoCategory',
                        'version': APP_VERSION,
                    })
                    return

                if path == '/extension/poll':
                    try:
                        deadline = time.monotonic() + 25
                        while True:
                            command = bridge.commands.get(timeout=max(0, deadline - time.monotonic()))
                            if command.get('expiresAt', 0) >= time.time() and command.get('id') in bridge.pending_ids:
                                break
                    except queue.Empty:
                        command = None
                    self._json(200, {'ok': True, 'command': command})
                    return

                self._json(404, {'ok': False, 'error': 'Not found'})

            def do_POST(self):
                if not self._authorized():
                    self._json(403, {
                        'ok': False,
                        'error': 'Chrome 확장프로그램 요청만 허용됩니다.',
                    })
                    return

                path = urlparse(self.path).path
                if path in ('/health', '/extension/poll', '/extension/info'):
                    try:
                        length = int(self.headers.get('Content-Length', '0'))
                        if not 0 < length <= 8192:
                            raise ValueError('length')
                        message = json.loads(self.rfile.read(length).decode('utf-8'))
                        if not isinstance(message, dict):
                            raise ValueError('message')
                        if message.get('type') == 'extension_info':
                            origin_id = self.headers.get('Origin', '').removeprefix('chrome-extension://')
                            if not bridge.receive_extension_info(message, origin_id):
                                self._json(409, {'ok': False, 'error': '오래된 응답입니다.'})
                                return
                        elif path == '/extension/info':
                            raise ValueError('type')
                    except (ValueError, TypeError, UnicodeError):
                        self._json(400, {'ok': False, 'error': '확장 정보 형식이 올바르지 않습니다.'})
                        return
                if path not in ('/health', '/extension/poll', '/extension/info', '/extension/result'):
                    self._json(404, {'ok': False, 'error': 'Not found'})
                    return
                self._mark_extension_connected()
                if path == '/extension/info':
                    self._json(200, {'ok': True, 'protocolVersion': 1})
                    return

                if path == '/health':
                    self._json(200, {
                        'ok': True,
                        'app': 'ChzzkAutoCategory',
                        'version': APP_VERSION,
                    })
                    return

                if path == '/extension/poll':
                    try:
                        deadline = time.monotonic() + 25
                        while True:
                            command = bridge.commands.get(timeout=max(0, deadline - time.monotonic()))
                            if command.get('expiresAt', 0) >= time.time() and command.get('id') in bridge.pending_ids:
                                break
                    except queue.Empty:
                        command = None
                    self._json(200, {'ok': True, 'command': command})
                    return

                if path != '/extension/result':
                    self._json(404, {'ok': False, 'error': 'Not found'})
                    return

                try:
                    length = int(self.headers.get('Content-Length', '0'))
                    if length <= 0 or length > 1024 * 1024:
                        raise ValueError('invalid body length')
                    payload = json.loads(self.rfile.read(length).decode('utf-8'))
                    command_id = str(payload.get('id') or '')
                    if not command_id:
                        raise ValueError('missing id')
                except Exception:
                    self._json(400, {'ok': False, 'error': '잘못된 결과 데이터입니다.'})
                    return

                if not bridge.accept_result(payload):
                    self._json(409, {'ok': False, 'error': '만료되었거나 알 수 없는 요청입니다.'})
                    return

                self._json(200, {'ok': True})

        try:
            self.server = ThreadingHTTPServer((self.host, self.port), Handler)
            self.server.daemon_threads = True
        except OSError as e:
            raise BridgeError(f'{self.host}:{self.port} 로컬 브리지를 열 수 없습니다: {e}') from e

        self.thread = threading.Thread(target=self.server.serve_forever, name='ChzzkLocalBridge', daemon=True)
        self.thread.start()
        self.add_log(f'로컬 브리지 시작 · http://{self.host}:{self.port} · 로그 /log')

    def stop(self):
        server = self.server
        self.server = None
        if server:
            self.add_log('로컬 브리지 종료')
            server.shutdown()
            server.server_close()
        self.thread = None

    def request(self, action, payload=None, timeout=20, cancelled=lambda: False):
        if not self.server:
            raise BridgeError('로컬 Chrome 브리지가 실행 중이 아닙니다.')
        if not self.connected:
            raise BridgeError('Chrome 확장프로그램이 연결되지 않았습니다. 확장프로그램과 치지직 스튜디오 로그인을 확인해 주세요.')

        if self.extension_status().get('compatibility') == '프로토콜 불일치':
            raise BridgeError('확장프로그램 버전이 호환되지 않습니다. 확장을 업데이트해 주세요.')
        if action not in ('settings', 'put_settings', 'search_categories', 'live_status'):
            raise BridgeError('지원하지 않는 명령입니다.')
        command_id = uuid.uuid4().hex
        command = {
            'id': command_id,
            'action': str(action),
            'payload': payload if isinstance(payload, dict) else {},
            'expiresAt': time.time() + max(1, float(timeout)),
        }
        self.add_log(f'Chrome 요청 전송 · {action}')
        with self.condition:
            self.pending_ids[command_id] = time.monotonic() + max(1, float(timeout))
        self.commands.put(command)

        deadline = time.monotonic() + max(1, float(timeout))
        with self.condition:
            while command_id not in self.results:
                if cancelled():
                    self.pending_ids.pop(command_id, None)
                    raise BridgeError('Chrome 요청이 취소되었습니다.')
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    self.pending_ids.pop(command_id, None)
                    self.add_log(f'Chrome 응답 시간 초과 · {action}', level='error')
                    raise BridgeError('Chrome 확장프로그램 응답 시간이 초과되었습니다.')
                self.condition.wait(timeout=min(remaining, 0.25))
            result = self.results.pop(command_id)
            self.pending_ids.pop(command_id, None)

        if not result.get('ok'):
            message = str(result.get('error') or 'Chrome 확장프로그램 작업에 실패했습니다.')
            self.add_log(f'Chrome 요청 실패 · {action} · {message}', level='error')
            raise BridgeError(message)
        self.add_log(f'Chrome 요청 완료 · {action}')
        return result.get('result')
