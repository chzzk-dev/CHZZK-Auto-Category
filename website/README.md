# CHZZK Auto Category 다운로드 사이트

정적 사이트 루트에 이 `website` 폴더의 내용을 배포합니다.
`/download/` 페이지는 `chzzk-dev/CHZZK-Auto-Category`의 최신 GitHub Release에서
`ChzzkAutoCategory-<버전>.msi`를 찾아 다운로드 버튼에 연결합니다.

릴리스에는 다음 파일을 올립니다.

- ChzzkAutoCategory-<버전>.msi
- SHA256SUMS.txt
- latest.json

Release가 없거나 MSI가 없으면 Releases 목록 링크를 표시합니다.
기존 Setup.exe와 ZIP은 이 페이지에서 선택하지 않습니다.
MSI에 필요한 앱 파일을 포함하고 기본적으로 Program Files에 설치합니다.
사용자 설정은 `%LOCALAPPDATA%\ChzzkAutoCategory`에 보존됩니다.
빌드와 구 설치본 전환 안내는 루트의 MSI_BUILD.md를 참고하세요.
