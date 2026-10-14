const GITHUB_REPO = 'chzzk-dev/CHZZK-Auto-Category';
const RELEASES_PAGE = `https://github.com/${GITHUB_REPO}/releases`;
const LATEST_API = `https://api.github.com/repos/${GITHUB_REPO}/releases/latest`;

const versionText = document.getElementById('versionText');
const sizeText = document.getElementById('sizeText');
const downloadButton = document.getElementById('downloadButton');
const releaseState = document.getElementById('releaseState');

function formatBytes(bytes) {
  if (!Number.isFinite(bytes) || bytes <= 0) return '설치 프로그램';
  const mb = bytes / 1024 / 1024;
  return `${mb.toFixed(mb >= 100 ? 0 : 1)} MB`;
}

async function loadLatestRelease() {
  try {
    const response = await fetch(LATEST_API, {
      cache: 'no-store',
      headers: { Accept: 'application/vnd.github+json' }
    });

    if (response.status === 404) {
      versionText.textContent = '준비 중';
      sizeText.textContent = '첫 Release 대기 중';
      releaseState.textContent = 'GitHub Releases에 첫 버전이 올라오면 이 버튼이 자동으로 최신 MSI를 가리킵니다.';
      downloadButton.textContent = 'GitHub Releases 보기';
      downloadButton.href = RELEASES_PAGE;
      downloadButton.removeAttribute('download');
      return;
    }

    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const release = await response.json();
    const version = String(release?.tag_name || '').replace(/^v/i, '') || 'latest';
    const assets = Array.isArray(release?.assets) ? release.assets : [];
    const setup = assets.find((item) => item?.name === `ChzzkAutoCategory-${version}.msi`);

    versionText.textContent = version;
    if (setup?.size) sizeText.textContent = formatBytes(Number(setup.size));

    if (setup?.browser_download_url) {
      downloadButton.href = setup.browser_download_url;
      downloadButton.textContent = 'MSI 다운로드';
      releaseState.textContent = `GitHub Release v${version}의 공식 설치 파일을 다운로드합니다.`;
    } else {
      downloadButton.href = RELEASES_PAGE;
      downloadButton.textContent = 'GitHub Releases 보기';
      downloadButton.removeAttribute('download');
      releaseState.textContent = '최신 Release에 MSI가 없어 Releases 페이지를 엽니다.';
    }
  } catch (error) {
    downloadButton.href = RELEASES_PAGE;
    downloadButton.textContent = 'GitHub Releases 보기';
    downloadButton.removeAttribute('download');
    releaseState.textContent = '최신 버전 정보를 불러오지 못했습니다. GitHub Releases에서 직접 확인해 주세요.';
  }
}

loadLatestRelease();
