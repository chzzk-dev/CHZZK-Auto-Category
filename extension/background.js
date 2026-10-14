const LOCAL_BASE = 'http://127.0.0.1:5000';
const STUDIO_URL = 'https://studio.chzzk.naver.com/';
const DOWNLOAD_PAGE = 'https://chzzk.dico.page/download/?from=extension&package=msi';
const KEEPALIVE_ALARM = 'chzzk-bridge-keepalive';
const EXTENSION_ID = chrome.runtime.id;
const BRIDGE_SESSION = crypto.randomUUID();
let infoSequence = 0;

function extensionInfo() {
  return { type: 'extension_info', extensionId: EXTENSION_ID, version: chrome.runtime.getManifest().version,
    protocolVersion: 1, browser: navigator.userAgent.includes('Edg/') ? 'Edge' : 'Chrome', connected: true,
    sessionId: BRIDGE_SESSION, sequence: ++infoSequence };
}

let loopRunning = false;
let lastBridgeOk = false;
let lastError = '';

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function setBridgeState(ok, error = '') {
  lastBridgeOk = Boolean(ok);
  lastError = String(error || '');
}

async function waitForTabComplete(tabId, timeoutMs = 15000) {
  const current = await chrome.tabs.get(tabId);
  if (current.status === 'complete') return;

  await new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      chrome.tabs.onUpdated.removeListener(listener);
      reject(new Error('치지직 스튜디오 페이지 로딩 시간이 초과되었습니다.'));
    }, timeoutMs);

    const listener = (updatedTabId, changeInfo) => {
      if (updatedTabId !== tabId || changeInfo.status !== 'complete') return;
      clearTimeout(timer);
      chrome.tabs.onUpdated.removeListener(listener);
      resolve();
    };

    chrome.tabs.onUpdated.addListener(listener);
  });
}

async function ensureStudioTab() {
  const tabs = await chrome.tabs.query({ url: 'https://studio.chzzk.naver.com/*' });
  let tab = tabs.find((item) => item.id) || null;

  if (!tab) {
    tab = await chrome.tabs.create({ url: STUDIO_URL, active: false });
  }

  await waitForTabComplete(tab.id);
  return tab.id;
}

async function executeCommand(command) {
  const tabId = await ensureStudioTab();
  const [{ result }] = await chrome.scripting.executeScript({
    target: { tabId },
    world: 'MAIN',
    args: [command],
    func: async (cmd) => {
      const API_BASE = 'https://api.chzzk.naver.com';
      const payload = cmd && typeof cmd.payload === 'object' ? cmd.payload : {};
      const channel = String(payload.channel || '').trim().toLowerCase();

      if (!/^[0-9a-f]{32}$/.test(channel)) {
        throw new Error('치지직 채널 ID 형식이 올바르지 않습니다.');
      }

      let method = 'GET';
      let path = '';
      let body;

      if (cmd.expiresAt && Date.now() / 1000 > cmd.expiresAt) throw new Error('만료된 요청입니다.');
      if (cmd.action === 'live_status') {
        path = `/service/v2/channels/${channel}/live-detail`;
      } else if (cmd.action === 'settings') {
        path = `/manage/v1/channels/${channel}/live-setting/normal`;
      } else if (cmd.action === 'put_settings') {
        method = 'PUT';
        path = `/manage/v1/channels/${channel}/live-setting/normal`;
        body = payload.settings;
        if (!body || typeof body !== 'object' || Array.isArray(body)) {
          throw new Error('방송 설정 요청 데이터가 올바르지 않습니다.');
        }
      } else if (cmd.action === 'search_categories') {
        const keyword = String(payload.keyword || '').trim();
        const params = new URLSearchParams({ keyword, size: '30', offset: '0' });
        path = `/manage/v1/auto-complete/categories?${params.toString()}`;
      } else {
        throw new Error('지원하지 않는 로컬 명령입니다.');
      }

      const response = await fetch(API_BASE + path, {
        method,
        credentials: 'include',
        signal: AbortSignal.timeout(15000),
        headers: {
          Accept: 'application/json',
          ...(body ? { 'Content-Type': 'application/json' } : {})
        },
        body: body ? JSON.stringify(body) : undefined
      });

      let responseBody = null;
      const text = await response.text();
      if (text) {
        try {
          responseBody = JSON.parse(text);
        } catch {
          responseBody = { raw: text.slice(0, 1000) };
        }
      }

      return {
        status: response.status,
        body: responseBody,
        retryAfter: response.headers.get('Retry-After')
      };
    }
  });

  if (!result || typeof result.status !== 'number') {
    throw new Error('치지직 API 결과를 확인할 수 없습니다.');
  }
  return result;
}

async function postResult(command, ok, result = null, error = '') {
  const response = await fetch(`${LOCAL_BASE}/extension/result`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Extension-Id': EXTENSION_ID
    },
    signal: AbortSignal.timeout(10000),
    body: JSON.stringify({
      id: command.id,
      ok,
      result,
      error
    })
  });

  if (!response.ok) {
    throw new Error(`로컬 브리지 결과 전송 실패 HTTP ${response.status}`);
  }
}

async function bridgeLoop() {
  if (loopRunning) return;
  loopRunning = true;
  let failures = 0;

  try {
    while (true) {
      try {
        // GET 요청은 확장프로그램 컨텍스트에서도 Origin 헤더가 생략될 수 있습니다.
        // 로컬 브리지가 chrome-extension:// Origin을 검증할 수 있도록 POST를 사용합니다.
        const response = await fetch(`${LOCAL_BASE}/extension/poll`, {
          method: 'POST',
          cache: 'no-store',
          headers: {
            'Content-Type': 'application/json',
            'X-Extension-Id': EXTENSION_ID
          },
          body: JSON.stringify(extensionInfo()),
          signal: AbortSignal.timeout(30000)
        });

        if (!response.ok) {
          throw new Error(`로컬 브리지 HTTP ${response.status}`);
        }

        setBridgeState(true);
        failures = 0;
        const data = await response.json();
        const command = data.command;

        if (!command) continue;

        try {
          const result = await executeCommand(command);
          await postResult(command, true, result, '');
        } catch (error) {
          await postResult(command, false, null, String(error?.message || error));
        }
      } catch (error) {
        setBridgeState(false, error?.message || error);
        failures++;
        if (failures >= 5) break; // Next Chrome alarm starts a new bounded reconnect batch.
        await sleep(Math.min(60000, 1500 * 2 ** (failures - 1)));
      }
    }
  } finally {
    loopRunning = false;
  }
}

async function installKeepalive() {
  try {
    await chrome.alarms.create(KEEPALIVE_ALARM, { periodInMinutes: 0.5 });
  } catch (_) {
    // 이미 만들어졌거나 브라우저가 정리 중인 경우는 무시합니다.
  }
}

chrome.runtime.onInstalled.addListener((details) => {
  installKeepalive();
  bridgeLoop();

  // Chrome Web Store에서 처음 설치한 사용자는 Windows 앱도 필요하므로
  // 최초 설치 시에만 다운로드 안내 페이지를 엽니다. 업데이트 때는 열지 않습니다.
  if (details.reason === 'install') {
    chrome.tabs.create({ url: DOWNLOAD_PAGE, active: true });
  }
});

chrome.runtime.onStartup.addListener(() => {
  installKeepalive();
  bridgeLoop();
});

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === KEEPALIVE_ALARM) {
    bridgeLoop();
  }
});

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type === 'bridge-status') {
    sendResponse({ connected: lastBridgeOk, error: lastError });
    return false;
  }

  if (message?.type === 'bridge-kick') {
    // A reconnect request is not evidence of a successful connection.
    bridgeLoop();
    sendResponse({ ok: true });
    return false;
  }

  if (message?.type === 'bridge-failed') {
    setBridgeState(false, message.error || '로컬 브리지 연결 실패');
    sendResponse({ ok: true });
    return false;
  }

  if (message?.type === 'open-studio') {
    chrome.tabs.create({ url: STUDIO_URL, active: true });
    sendResponse({ ok: true });
    return false;
  }

  return false;
});

installKeepalive();
bridgeLoop();
