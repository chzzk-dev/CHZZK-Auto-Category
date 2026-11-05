# Pratfall 감지 보완 (4.12.9)

## 실제 원인과 확인 자료

2026-10-15에 Discord 공개 응답을 직접 조회했습니다.

- URL: https://discord.com/api/v10/applications/detectable
- `name`: `Pratfall`
- Discord ID: `1468444820484784333`
- `executables`: `[]`
- `third_party_skus`: Steam `4244510`

이 레코드는 이름만 존재하므로 실행 파일을 인덱스로 만드는 기존 파서에서 빠집니다. Steam 한국어 매칭도 프로세스 감지 이후에 실행되기 때문에 기존 Steam 키 설정만으로 해결되지 않습니다.

실행 파일 이름을 게임 제목에서 추측하지 않고 아래 실제 응답을 대조했습니다.

- SteamCMD 공개 app_info 조회: https://api.steamcmd.net/v1/info/4244510
- `data.4244510.common.name`: `Pratfall`
- 공개 Windows 실행 옵션 0·1·5의 `executable`: `Pratfall.exe`
- `Pratfall.console.exe`는 `development` 브랜치 옵션이며 보완 감지에 추가하지 않습니다.
- `GameLauncher.exe`는 게임 본체가 아니며 기존 런처 제외를 유지합니다.
- Steam 한국어 상세: https://store.steampowered.com/api/appdetails?appids=4244510&l=koreana&cc=KR
- 실제 `steam_appid`: `4244510`, `name`: `프랫폴`

SteamCMD API는 Valve 공식 Web API가 아닌 외부 공개 조회 서비스입니다. 이번 확인에만 이용하며 앱 실행 시 이 서비스를 추가 호출하거나 새 라이브러리를 설치하지 않습니다.

## 구현

`autodetect.py`의 `VERIFIED_EXECUTABLE_COMPATIBILITY`에 확인된 실제 실행 파일과 Discord ID, 한국어 별칭을 보관합니다. `with_verified_executable_compatibility()`가 원격 목록 갱신 및 기존 캐시 최초 로드에 한 번 적용됩니다. 매 스캔마다 전체 Discord 목록을 다시 분석하지 않습니다.

이 규칙은 게임 감지만 보완합니다. 치지직 카테고리 ID를 고정하거나 존재한다고 가정하지 않습니다. 기존 Steam 이름 조회와 치지직 검색·검증을 거치며, 미확정·검색 실패 항목은 적용 가능한 대기열에 넣지 않습니다. 수동 규칙이 우선하고 동일한 실행 파일을 다른 게임도 쓰는 경우 기존 확인 필요 처리를 유지합니다.

## 테스트 범위

`tests/test_pratfall_detection.py`는 Discord의 빈 실행 파일 응답, 새 목록 갱신, 기존 유효 캐시, 오프라인, 대소문자 중복, 런처 제외, 기존 목록과의 병합·충돌, 한국어 카테고리 모의 검색, 수동 우선, 검색 실패를 검증합니다. 사용자 PC의 실제 Pratfall 실행 및 실제 치지직 방송 변경은 테스트 환경에 없어 별도 확인이 필요합니다.

# 롤·롤체 독립 클라이언트 자동 감지

라이엇은 [LoL 26.22 패치 노트](https://www.leagueoflegends.com/en-us/news/game-updates/league-of-legends-patch-26-22-notes/)와 [TFT 18.6 패치 노트](https://teamfighttactics.leagueoflegends.com/en-au/news/game-updates/teamfight-tactics-patch-18-6/)에서 TFT 독립 클라이언트 출시를 안내했습니다. 실행 파일 이름은 2026-11-05 사용자가 제공한 다음 경로를 근거로 추가했습니다.

`C:\Riot Games\Teamfight Tactics\Live\TFT\Binaries\Win64\TFTClient-Win64-Shipping.exe`

- 감지는 설치 위치와 무관하게 실행 파일 이름만 대소문자 구분 없이 비교합니다. 프로세스 메모리·모듈·명령행을 조회하지 않습니다.
- 롤은 `LeagueClient.exe` 또는 `League of Legends.exe`, 롤체는 `TFTClient-Win64-Shipping.exe`로 구분합니다. UX·렌더러·공용 Riot 런처는 계속 제외합니다.
- 처음 실행하거나 Discord 목록이 오프라인·구형 캐시인 경우에도 호환 항목을 추가합니다. 예전 Discord 목록에 두 게임이 같은 롤 실행 파일로 들어 있어도 분리합니다.
- 매 실행 시 모드 선택창과 공유 실행 파일 빠른 선택 버튼을 제거합니다. 저장된 수동·자동 롤체 연결은 실제 카테고리 이름·ID를 보존하여 새 TFT 실행 파일로 이전합니다. 다른 게임의 사용자 연결은 유지합니다.
- TFT가 실행 중이면 남아 있는 롤 대기실은 대표 게임 후보에서 제외합니다. 실제 롤 경기와 TFT가 동시에 실행 중이면 기존 다중 게임 대표 선택 정책을 사용합니다.
- TFT 한국어 이름을 우선 검색하고 `전략적 팀 전투 : 시즌명`처럼 콜론 뒤에 붙는 시즌 부제만 허용합니다. 모바일·다른 게임은 제외하며, 실제 ID가 다른 동명 카테고리가 여러 개면 기존 카테고리 확인 절차를 유지합니다. 카테고리 ID를 추측하거나 고정하지 않습니다.
- 새 TFT 실행 파일과 맞지 않는 과거 카테고리 캐시는 온라인·오프라인 모두 재사용하지 않습니다.

`tests/test_tft_standalone.py`는 제공된 경로·대소문자, 오프라인 초기 실행·유효한 구형 캐시, Discord 공유 항목 분리, 시즌명과 실제 반환 ID, 구형 수동·자동 연결 이전, 롤 대기실과 TFT 동시 실행, 롤↔TFT 전환, 종료·취소·검색 오류와 잘못된 검증 캐시를 모의 응답으로 검증합니다. Qt 검사에서는 모드 버튼이 사라진 상세 화면과 대시보드 갱신을 확인합니다. 실제 사용자 PC의 TFT 실행 및 실제 방송 카테고리 변경은 이 환경에서 수행하지 않았습니다.
