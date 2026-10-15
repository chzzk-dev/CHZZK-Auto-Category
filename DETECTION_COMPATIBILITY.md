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
