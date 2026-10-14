# Chrome Web Store 등록용 초안

## 확장 0.5.3 — MSI 다운로드 전환

- 팝업의 Setup.exe 직접 링크를 최신 MSI 다운로드 안내 페이지로 변경했습니다.
- 최초 설치 시에도 같은 MSI 안내 페이지를 엽니다. 확장 업데이트 때는 새 탭을 자동으로 열지 않습니다.
- Windows 앱 4.11.1 MSI와 함께 사용합니다. 확장 버전은 별도로 0.5.3입니다.
- 기존 웹스토어 항목에 새 확장 ZIP을 업로드하세요. 스토어 게시 작업은 별도로 해야 합니다.
- `website/` 내용을 다운로드 사이트에 먼저 배포하고 GitHub Release에 MSI를 올려야 실제 다운로드가 가능합니다.
- 확장 ZIP에는 manifest.json과 background.js 등이 최상위에 들어갑니다. 앱 소스 ZIP을 웹스토어에 올리지 마세요.


## 이름

CHZZK Auto Category Bridge

## 짧은 설명

로컬 CHZZK Auto Category 앱과 Chrome의 치지직 스튜디오 로그인 상태를 연결해 방송 카테고리 자동 변경을 지원합니다.

## 상세 설명

CHZZK Auto Category Bridge는 Windows용 CHZZK Auto Category 앱과 함께 사용하는 확장프로그램입니다.

주요 기능:

- 로컬 앱(`127.0.0.1:5000`)과 연결
- 치지직 스튜디오 로그인 상태를 이용한 방송 설정 조회
- 게임 감지 결과에 따른 치지직 카테고리 변경
- 기존 방송 제목, 태그 등 확인된 일반 설정값을 유지한 카테고리 변경

확장프로그램은 로그인 쿠키 문자열을 로컬 앱으로 전달하지 않습니다. 인증이 필요한 요청은 치지직 스튜디오 페이지 컨텍스트에서 수행하고 API 결과만 로컬 앱에 전달합니다.

## 권한 사용 목적

### scripting

치지직 스튜디오 페이지에서 인증된 API 요청을 실행하기 위해 사용합니다.

### alarms

로컬 앱 연결 작업을 주기적으로 다시 시작하기 위해 사용합니다.

### host permissions

- `https://studio.chzzk.naver.com/*`: 치지직 스튜디오 탭 연결
- `http://127.0.0.1:5000/*`: 사용자 PC에서 실행되는 CHZZK Auto Category 앱과 통신

## 개인정보 관련 설명

처리하는 데이터:

- 사용자가 설정한 치지직 채널 ID
- 카테고리 검색 키워드
- 방송 설정 조회 결과
- 카테고리 변경에 필요한 방송 설정 payload
- 요청 성공/실패 상태

확장프로그램은 이 데이터를 개발자의 외부 서버로 전송하지 않으며, 사용자 PC의 로컬 앱과 치지직 API 사이에서만 처리합니다.

실제 배포 전에 본인의 최종 구현과 일치하는지 반드시 다시 확인하세요.


## 게시된 Chrome Web Store ID

`jeefpiogpjbphganmnooglppcdicinoh`

이 ID는 Python 로컬 브리지의 허용 확장 ID 기본값으로 포함되어 있습니다. Chrome Web Store용 `manifest.json`에는 ID를 직접 적지 않습니다. 동일한 Web Store 항목에 새 패키지를 업로드하면 기존 ID가 유지됩니다.
