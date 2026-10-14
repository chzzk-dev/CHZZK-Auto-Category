const DOWNLOAD_PAGE = 'https://chzzk.dico.page/download/?from=extension&package=msi';
const LOCAL_HEALTH = 'http://127.0.0.1:5000/health';
const EXTENSION_ID = chrome.runtime.id;
const status = document.getElementById('status');
const refreshButton = document.getElementById('refresh');
let probeRunning = false;

function showStatus(text, ok = false) {
  status.textContent = text;
  status.className = ok ? 'status ok' : 'status error';
}

async function cachedStatus() {
  try {
    const result = await chrome.runtime.sendMessage({ type: 'bridge-status' });
    if (result?.connected) {
      showStatus('연결됨 · 로컬 앱과 통신 중', true);
      return;
    }
  } catch (_) {
    // 서비스 워커가 재시작되는 순간에는 메시지가 실패할 수 있습니다.
  }

  showStatus('연결 대기 · 앱 실행 후 아래 버튼을 눌러 로컬 연결을 허용해 주세요.');
}

async function probeLocalBridge() {
  if (probeRunning) return;
  probeRunning = true;
  refreshButton.disabled = true;
  showStatus('127.0.0.1:5000 연결 확인 중…');

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 4000);

  try {
    // Chrome 142+에서는 이 팝업 문서에서 요청을 한 번 발생시켜야
    // Local Network Access 권한 프롬프트를 표시할 수 있습니다.
    // POST를 사용해야 Chrome이 chrome-extension:// Origin을 함께 보내
    // 로컬 앱이 요청 출처를 검증할 수 있습니다.
    const response = await fetch(LOCAL_HEALTH, {
      method: 'POST',
      cache: 'no-store',
      signal: controller.signal,
      headers: {
        'Content-Type': 'application/json',
        'X-Extension-Id': EXTENSION_ID
      },
      body: '{}'
    });

    if (!response.ok) {
      if (response.status === 403) {
        throw new Error(`HTTP 403 · 앱의 Chrome 확장 ID를 ${EXTENSION_ID} 로 설정했는지 확인해 주세요.`);
      }
      throw new Error(`HTTP ${response.status}`);
    }

    const data = await response.json();
    if (!data?.ok) {
      throw new Error('로컬 앱 응답 형식이 올바르지 않습니다.');
    }

    await chrome.runtime.sendMessage({ type: 'bridge-kick' });
    showStatus('연결됨 · 로컬 앱과 통신 중', true);
  } catch (error) {
    const message = error?.name === 'AbortError'
      ? '연결 실패 · 127.0.0.1:5000 응답 시간이 초과되었습니다.'
      : `연결 실패 · ${String(error?.message || error)}`;

    showStatus(message);

    try {
      await chrome.runtime.sendMessage({
        type: 'bridge-failed',
        error: message
      });
    } catch (_) {
      // 표시가 이미 되어 있으므로 무시합니다.
    }
  } finally {
    clearTimeout(timer);
    refreshButton.disabled = false;
    probeRunning = false;
  }
}

refreshButton.addEventListener('click', probeLocalBridge);

document.getElementById('studio').addEventListener('click', async () => {
  await chrome.runtime.sendMessage({ type: 'open-studio' });
  window.close();
});

cachedStatus();

// 팝업이 열려 있는 동안 로컬 앱 연결 상태를 5초마다 자동으로 다시 확인합니다.
const statusTimer = setInterval(() => {
  if (!document.hidden) probeLocalBridge();
}, 5000);
window.addEventListener('unload', () => clearInterval(statusTimer));

document.getElementById('downloadApp').addEventListener('click', async () => {
  await chrome.tabs.create({ url: DOWNLOAD_PAGE, active: true });
  window.close();
});

document.getElementById('log').addEventListener('click', async () => {
  await chrome.tabs.create({ url: "http://127.0.0.1:5000/log", active: true });
  window.close();
});
