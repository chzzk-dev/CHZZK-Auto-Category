# 변경 기록

릴리스를 게시하면 이 파일에 버전, 한국 시간 기준 날짜, 변경 사항과 커밋 링크가 자동으로 기록됩니다.
배포 전 사용자에게 설명할 내용은 아래 `미배포` 항목에 추가할 수 있습니다.

## 미배포

- 아직 기록할 변경 사항이 없습니다.

## [4.12.11](https://github.com/chzzk-dev/CHZZK-Auto-Category/releases/tag/v4.12.11) — 2026-10-16 (KST)

### 변경 사항

- 재배포: `Buckshot Roulette.exe` 감지 시 `벅샷 룰렛`을 검색하고 검증된 치지직 카테고리에 연결합니다.
- Discord의 Steam App ID를 보존하고 API 키 없이 한국어 게임 이름을 직접 조회합니다.
- Steam 이름 검색·Web API ID 확인 단계를 생략하여 App ID가 있는 게임의 조회를 줄이고, 기존 캐시는 한 번 갱신합니다.
- 잘못된 App ID·다중 에디션·DLC는 자동 연결하지 않으며 수동 규칙과 치지직 검증, 기존 키 기반 보조 조회를 유지합니다.
- Steam 연결 확인과 빌드 검증에 키 없는 상점 조회를 적용하고 STEAM_WEB_API는 선택적인 보조 연결로 유지합니다.

### 커밋

- Use Discord Steam app IDs for keyless Korean title lookup in 4.12.11 ([4453f84](https://github.com/chzzk-dev/CHZZK-Auto-Category/commit/4453f84e0e205bcb1ee7c2d6cafb5c6e9157b997))

[전체 변경 비교](https://github.com/chzzk-dev/CHZZK-Auto-Category/compare/v4.12.10...v4.12.11)

### 설치 파일

- `ChzzkAutoCategory-4.12.11.msi`
- `SHA256SUMS.txt`에서 설치 파일의 SHA-256을 확인할 수 있습니다.
- 기존 MSI 설치본은 새 MSI로 업그레이드하며 사용자 설정을 유지합니다.

## [4.12.10](https://github.com/chzzk-dev/CHZZK-Auto-Category/releases/tag/v4.12.10) — 2026-10-15 (KST)

### 변경 사항

- 로그를 시간·유형·내용으로 정렬하고 중복 유형 표기를 제거합니다.
- 분석·검색·검증 중간 과정은 기본 화면에서 숨기고 세부 과정 표시로 확인합니다. 상세 파일 기록은 유지합니다.
- 동일한 연결 성공과 반복 매칭 결과를 정리하며 실제 연결 오류·복구·카테고리 변경·게임 재실행은 계속 기록합니다.
- 화면 지우기 후 필터를 바꿔도 지운 기록이 되살아나지 않도록 수정하고 읽던 스크롤 위치를 유지합니다.

### 커밋

- Keep game exit logs reliable across snapshot events \[cancel obsolete builds\] ([97652c2](https://github.com/chzzk-dev/CHZZK-Auto-Category/commit/97652c21a0f3cc51b1c7076008a541ed77a3fae3))
- Preserve one-line copied activity logs \[cancel obsolete builds\] ([06566c5](https://github.com/chzzk-dev/CHZZK-Auto-Category/commit/06566c5681d70350fba29726a51b549f2893489c))
- Simplify activity logs and suppress repeated polling messages in 4.12.10 ([f549bad](https://github.com/chzzk-dev/CHZZK-Auto-Category/commit/f549bad4f3a487b565e0de9063fd88056157c997))

[전체 변경 비교](https://github.com/chzzk-dev/CHZZK-Auto-Category/compare/v4.12.9...v4.12.10)

### 설치 파일

- `ChzzkAutoCategory-4.12.10.msi`
- `SHA256SUMS.txt`에서 설치 파일의 SHA-256을 확인할 수 있습니다.
- 기존 MSI 설치본은 새 MSI로 업그레이드하며 사용자 설정을 유지합니다.

## [4.12.9](https://github.com/chzzk-dev/CHZZK-Auto-Category/releases/tag/v4.12.9) — 2026-10-15 (KST)

### 변경 사항

- 4.12.9 재배포: `Smilemo.exe`는 `스마일모`로 검색하고 검증된 카테고리에 연결합니다. 한국어 연결 규칙이 정리 과정에서 사라지지 않도록 보완합니다.
- Discord 목록에 있지만 실행 파일 정보가 비어 있던 Pratfall을 실제 게임 파일 `Pratfall.exe`로 감지하도록 보완합니다.
- Steam 한국어 제목 `프랫폴`을 별칭에 추가하고 기존 카테고리 검색·검증 후에만 자동 연결합니다.
- 기존 Discord 캐시에도 보완 규칙을 즉시 적용하며 설정 초기화나 캐시 삭제가 필요하지 않습니다.
- 런처·오류 보고 프로그램 제외, 수동 규칙 우선, 실행 파일 충돌 시 확인 대기 동작을 유지합니다.

### 커밋

- Fix Pratfall detection with verified executable compatibility in 4.12.9 ([9569e6e](https://github.com/chzzk-dev/CHZZK-Auto-Category/commit/9569e6e0727647473f662d6d1da7bd6101f76388))

[전체 변경 비교](https://github.com/chzzk-dev/CHZZK-Auto-Category/compare/v4.12.8...v4.12.9)

### 설치 파일

- `ChzzkAutoCategory-4.12.9.msi`
- `SHA256SUMS.txt`에서 설치 파일의 SHA-256을 확인할 수 있습니다.
- 기존 MSI 설치본은 새 MSI로 업그레이드하며 사용자 설정을 유지합니다.

## [4.12.8](https://github.com/chzzk-dev/CHZZK-Auto-Category/releases/tag/v4.12.8) — 2026-10-15 (KST)

### 변경 사항

- Steam 기본 연결을 Actions Secret `STEAM_WEB_API`에서 자동 설정하여 사용자 키 입력 없이 한국어 게임 이름 매칭을 사용합니다.
- 앱 시작 시 Steam 연결을 백그라운드에서 확인하고 Steam 화면의 키 입력·저장·삭제·발급 버튼을 제거하고 토글·연결 상태·다시 확인만 표시합니다. 기존 개인 키와 사용자 설정을 보존합니다.
- 실제 컴파일된 EXE의 Steam 기본 키 인증·한국어 조회를 릴리스 검증에 추가합니다.
- 4.12.8 새 정식 릴리스로 게시하여 기존 4.12.7의 자동 업데이트 경로를 유지합니다.

### 커밋

- Release 4.12.8 with automatic Steam credentials and simple connection controls ([6071630](https://github.com/chzzk-dev/CHZZK-Auto-Category/commit/6071630ef029e314e2a56c7b941a4f993560024f))

[전체 변경 비교](https://github.com/chzzk-dev/CHZZK-Auto-Category/compare/v4.12.7...v4.12.8)

### 설치 파일

- `ChzzkAutoCategory-4.12.8.msi`
- `SHA256SUMS.txt`에서 설치 파일의 SHA-256을 확인할 수 있습니다.
- 기존 MSI 설치본은 새 MSI로 업그레이드하며 사용자 설정을 유지합니다.

## [4.12.7](https://github.com/chzzk-dev/CHZZK-Auto-Category/releases/tag/v4.12.7) — 2026-10-15 (KST)

### 변경 사항

- 4.12.7 재배포: 감지된 게임을 Steam API 키로 확인한 뒤 한국어 이름을 조회하고 치지직 카테고리에 우선 매칭합니다.
- Steam 연결 관리, 개인 키의 Windows DPAPI 저장, 게임별 조회 캐시와 요청 제한·오류 시 기존 매칭 전환을 추가합니다.
- 4.12.7 재배포: `MIMESIS.exe`의 검색명을 `미메시스`로 고정하고 실제로 확인된 치지직 카테고리에 자동 연결합니다.
- 동일 버전 MSI 재설치 시 기존 설치와 설정을 보존하며 제품 등록을 하나로 유지합니다.

- 대시보드를 상단 상태 요약 3개, 현재 게임 정보, 최근 활동 순서로 재배치하고 중복 감지 카드를 통합합니다.
- 게임 카드의 불필요한 높이와 여백을 줄이고 실행 파일·카테고리·감지 방식·매칭 상태를 가로로 정렬합니다.
- 게임 관리와 전체 로그 버튼을 제목 옆에 작게 배치하고 최근 활동 5건의 시간·내용을 구분선으로 정돈합니다.
- 기본 창을 1360×860으로 조정하고 최소 1200×820 및 기존 기능·설정·연결 정보는 유지합니다.

### 커밋

- Compact dashboard cards and align game details and activity in 4.12.7 ([279edb7](https://github.com/chzzk-dev/CHZZK-Auto-Category/commit/279edb7172905e40f9c4158f8ed4864c6a119899))

[전체 변경 비교](https://github.com/chzzk-dev/CHZZK-Auto-Category/compare/v4.12.6...v4.12.7)

### 설치 파일

- `ChzzkAutoCategory-4.12.7.msi`
- `SHA256SUMS.txt`에서 설치 파일의 SHA-256을 확인할 수 있습니다.
- 기존 MSI 설치본은 새 MSI로 업그레이드하며 사용자 설정을 유지합니다.

## [4.12.6](https://github.com/chzzk-dev/CHZZK-Auto-Category/releases/tag/v4.12.6) — 2026-10-15 (KST)

### 변경 사항

- 롤 클라이언트를 실행하면 먼저 롤/롤토체스 선택 창을 표시합니다. 이전 연결이 있어도 새 실행에서는 선택을 기다립니다.
- 대기실에서 게임으로 전환할 때는 다시 묻지 않으며, 클라이언트를 완전히 종료한 뒤 다시 실행하면 새로 선택합니다.
- 선택 창을 닫으면 자동 변경을 보류하고, 종료된 게임의 지연 검색 결과는 저장·적용하지 않습니다.
- 게임 설정·카테고리 선택·실행 파일 선택 등 서브 창의 기본 윈도우 제목 표시줄을 제거하고 내부 닫기 버튼을 제공합니다.

### 커밋

- Ask LoL or TFT on each client launch and unify frameless subwindows in 4.12.6 ([da353d4](https://github.com/chzzk-dev/CHZZK-Auto-Category/commit/da353d489773f9b0e599f1d13b0390234568b544))

[전체 변경 비교](https://github.com/chzzk-dev/CHZZK-Auto-Category/compare/v4.12.5...v4.12.6)

### 설치 파일

- `ChzzkAutoCategory-4.12.6.msi`
- `SHA256SUMS.txt`에서 설치 파일의 SHA-256을 확인할 수 있습니다.
- 기존 MSI 설치본은 새 MSI로 업그레이드하며 사용자 설정을 유지합니다.

## [4.12.5](https://github.com/chzzk-dev/CHZZK-Auto-Category/releases/tag/v4.12.5) — 2026-10-15 (KST)

### 변경 사항

- 데스크톱 기본 창을 1440×960으로 확대하고 대시보드 카드 간격과 비율을 정리합니다.
- 자동화·프로그램 설정을 2열 카드와 왼쪽 설명/오른쪽 컨트롤 구조로 개편합니다.
- 체크박스를 키보드 조작을 지원하는 좌우 토글로 바꾸고 버튼·선택창·스크롤바 스타일을 통일합니다.
- 설정 저장 버튼을 화면 하단에 고정해 스크롤 위치와 관계없이 저장할 수 있게 합니다.
- 공식 API를 필수 사용으로 고정하고 빌드 인증 정보로 앱 시작 시 연결 상태를 자동 확인합니다. 인증 정보가 없는 빌드는 상태를 명확히 안내합니다.

### 커밋

- Isolate official API UI test logging to permit Windows temporary-profile cleanup ([c25ca5f](https://github.com/chzzk-dev/CHZZK-Auto-Category/commit/c25ca5f98ce818e046b41eaafb8ea65e555b0762))
- Refresh settings with accessible toggles and automatic official API setup in 4.12.5 ([402629e](https://github.com/chzzk-dev/CHZZK-Auto-Category/commit/402629e78784a63aa147703f462b0c913fcaa61e))

[전체 변경 비교](https://github.com/chzzk-dev/CHZZK-Auto-Category/compare/v4.12.4...v4.12.5)

### 설치 파일

- `ChzzkAutoCategory-4.12.5.msi`
- `SHA256SUMS.txt`에서 설치 파일의 SHA-256을 확인할 수 있습니다.
- 기존 MSI 설치본은 새 MSI로 업그레이드하며 사용자 설정을 유지합니다.

## [4.12.4](https://github.com/chzzk-dev/CHZZK-Auto-Category/releases/tag/v4.12.4) — 2026-10-15 (KST)

### 변경 사항

- 롤토체스 빠른 선택에서 TFT 카테고리의 시즌 부제(콜론 뒤 이름) 때문에 연결에 실패하던 문제를 수정합니다.
- 기본 이름으로 검색하고 비교하되 실제 검색 결과의 카테고리 ID와 전체 이름을 저장합니다.
- 다른 게임이나 서로 다른 ID의 후보가 여러 개면 임의로 연결하지 않습니다.

### 커밋

- Match TFT seasonal category subtitles in quick selection for stable 4.12.4 ([7ef7c71](https://github.com/chzzk-dev/CHZZK-Auto-Category/commit/7ef7c717e7f615d49d765a723bf2e55e63bb7eb8))

[전체 변경 비교](https://github.com/chzzk-dev/CHZZK-Auto-Category/compare/v4.12.3...v4.12.4)

### 설치 파일

- `ChzzkAutoCategory-4.12.4.msi`
- `SHA256SUMS.txt`에서 설치 파일의 SHA-256을 확인할 수 있습니다.
- 기존 MSI 설치본은 새 MSI로 업그레이드하며 사용자 설정을 유지합니다.

## [4.12.3](https://github.com/chzzk-dev/CHZZK-Auto-Category/releases/tag/v4.12.3) — 2026-10-14 (KST)

### 변경 사항

- 게임 설정을 게임 이름·방송 카테고리·사용 버튼 중심의 간편 창으로 바꿉니다.
- 롤/롤토체스는 두 버튼으로 선택하고 실제 검색 결과를 확인한 뒤 연결을 저장합니다.
- 기술 정보와 별칭·실행 파일·연결 방식 변경은 접힌 고급 설정으로 이동합니다.
- 게임 행 클릭은 선택만 수행하며 간편 설정 버튼 또는 더블클릭으로 설정 창을 엽니다.

### 커밋

- Simplify game setup and add verified one-click LoL or TFT selection for 4.12.3 ([d6275f0](https://github.com/chzzk-dev/CHZZK-Auto-Category/commit/d6275f095b6aaedca9aa00dda968eb82c4f86963))

[전체 변경 비교](https://github.com/chzzk-dev/CHZZK-Auto-Category/compare/v4.12.2...v4.12.3)

### 설치 파일

- `ChzzkAutoCategory-4.12.3.msi`
- `SHA256SUMS.txt`에서 설치 파일의 SHA-256을 확인할 수 있습니다.
- 기존 MSI 설치본은 새 MSI로 업그레이드하며 사용자 설정을 유지합니다.

## [4.12.2](https://github.com/chzzk-dev/CHZZK-Auto-Category/releases/tag/v4.12.2) — 2026-10-14 (KST)

### 변경 사항

- 롤/TFT 모드 확인 대기를 중복 항목으로 삭제한 뒤 재등록하던 문제를 수정합니다.
- 같은 게임을 감지할 때 정리 로그와 확인 알림이 반복되지 않도록 합니다.
- 게임 종료 또는 수동 연결 시 대기 항목을 정상 정리하며, 근거 없는 롤/TFT 자동 선택은 방지합니다.

### 커밋

- Fix repeated cleanup and re-registration of LoL/TFT mode prompts in 4.12.2 ([a154a34](https://github.com/chzzk-dev/CHZZK-Auto-Category/commit/a154a34baa77668708c99593960e7be7d25515ac))

[전체 변경 비교](https://github.com/chzzk-dev/CHZZK-Auto-Category/compare/v4.12.1...v4.12.2)

### 설치 파일

- `ChzzkAutoCategory-4.12.2.msi`
- `SHA256SUMS.txt`에서 설치 파일의 SHA-256을 확인할 수 있습니다.
- 기존 MSI 설치본은 새 MSI로 업그레이드하며 사용자 설정을 유지합니다.

## [4.12.1](https://github.com/chzzk-dev/CHZZK-Auto-Category/releases/tag/v4.12.1) — 2026-10-14 (KST)

### 변경 사항

- 쿠키앤크림 스타일의 크림 배경·다크그레이 카드·두꺼운 흰 테두리로 데스크톱 UI를 전면 개편합니다.
- 대시보드를 큰 게임 패널, 오른쪽 연결·자동화 패널, 하단 감지·카테고리·활동 패널로 재배치합니다.
- 메뉴·게임 목록·설정·연결·로그·팝업과 지원 아이콘의 스타일 및 대비를 통일합니다.
- 기존 감지·자동 변경·확장 연결·사용자 설정은 유지합니다.
- 4.12.1은 정식 최신 릴리스로 배포하며 기존 안정 버전의 업데이트 확인 대상에 포함됩니다.

### 커밋

- Publish cookie-and-cream desktop redesign as stable 4.12.1 ([d2fdb4b](https://github.com/chzzk-dev/CHZZK-Auto-Category/commit/d2fdb4bfca8abc3d784d17f2a777fdd127e351f6))

[전체 변경 비교](https://github.com/chzzk-dev/CHZZK-Auto-Category/compare/v4.12.0...v4.12.1)

### 설치 파일

- `ChzzkAutoCategory-4.12.1.msi`
- `SHA256SUMS.txt`에서 설치 파일의 SHA-256을 확인할 수 있습니다.
- 기존 MSI 설치본은 새 MSI로 업그레이드하며 사용자 설정을 유지합니다.

## [4.12.0](https://github.com/chzzk-dev/CHZZK-Auto-Category/releases/tag/v4.12.0) — 2026-10-14 (KST)

### 변경 사항

- 밝은 설치 UI와 공통 테마/아이콘을 사용하는 대시보드·게임 목록·자동화·연결·설정·로그 6개 페이지로 개편합니다.
- 게임별 검색·검증 상태와 적용 대기를 분리하며 수동 규칙, 시리즈/버전 구분, 종료된 게임의 지연 결과 차단을 강화합니다.
- Discord ID와 사용자 별칭을 유지하고 검증 캐시를 재사용합니다. LoL/TFT는 실행 파일만으로 추측하지 않습니다.
- 확장프로그램 0.6.0에서 실제 manifest 버전·프로토콜·heartbeat를 전달하며 오래된 응답과 중복 요청을 차단합니다.
- 앱 업데이트는 기본 3시간, 카테고리 동기화는 기본 6시간이며 두 자동 주기의 최소값은 1시간입니다.
- 설정 마이그레이션 원본 백업, 순환 로그와 민감 정보 마스킹, 단일 업데이터 잠금 및 실패 후 기존 앱 재실행 경로를 추가합니다.
- Windows CI에 Qt DPI 렌더링과 실제 보호 EXE의 오프라인 아이콘 검사를 추가합니다. 기존 MSI 설치·업그레이드·제거 검증은 유지합니다.
- 4.12.0은 사전 릴리스 후보입니다. GitHub 반영과 게시에는 사용자 승인이 필요하며 Chrome Web Store 게시와는 별개입니다.

### 커밋

- Redesign desktop UI and strengthen verified category automation for 4.12.0 ([49e59fc](https://github.com/chzzk-dev/CHZZK-Auto-Category/commit/49e59fcc1ba7497736feb713b602c3702feefd08))

[전체 변경 비교](https://github.com/chzzk-dev/CHZZK-Auto-Category/compare/v4.11.5...v4.12.0)

### 설치 파일

- `ChzzkAutoCategory-4.12.0.msi`
- `SHA256SUMS.txt`에서 설치 파일의 SHA-256을 확인할 수 있습니다.
- 기존 MSI 설치본은 새 MSI로 업그레이드하며 사용자 설정을 유지합니다.

## [4.11.5](https://github.com/chzzk-dev/CHZZK-Auto-Category/releases/tag/v4.11.5) — 2026-10-14 (KST)

### 변경 사항

- 4.11.5는 기존 업데이터의 반복 오류를 막기 위해 사전 릴리스로 게시합니다. 자동 업데이트에는 노출되지 않으며 MSI를 직접 설치해야 합니다.
- 공백이 있는 설치 경로의 MSI 인수 따옴표 처리를 수정해 자동 업데이트의 오류 1639를 해결합니다.
- Windows CI에서 실제 MSI 설치·업그레이드·제거와 사용자 설정 보존을 확인한 뒤 릴리스합니다.
- 기존 업데이터에 이 오류가 있는 경우 이번 수정본 MSI를 한 번 직접 실행해 업데이트하세요.

### 커밋

- test: validate invalid MSI property syntax without interactive error dialogs ([cdc297a](https://github.com/chzzk-dev/CHZZK-Auto-Category/commit/cdc297acab043d18d7965b4b3377a6f3b8716a24))
- ci: publish the updater repair as a manual prerelease \[cancel obsolete builds\] ([8bc2d0f](https://github.com/chzzk-dev/CHZZK-Auto-Category/commit/8bc2d0f8f310eff8f476885ccb6a2ad74adb264c))
- test: select an available stable MSI baseline and verify both updated executables ([ab79759](https://github.com/chzzk-dev/CHZZK-Auto-Category/commit/ab797597bc9c9e285310ee59a3dd9185a2c94e9e))
- fix: quote MSI property values correctly and verify real upgrades for 4.11.5 ([bce1ed8](https://github.com/chzzk-dev/CHZZK-Auto-Category/commit/bce1ed8e740250b72a9129ce5559ab63b497e046))

[전체 변경 비교](https://github.com/chzzk-dev/CHZZK-Auto-Category/compare/v4.11.4...v4.11.5)

### 설치 파일

- `ChzzkAutoCategory-4.11.5.msi`
- `SHA256SUMS.txt`에서 설치 파일의 SHA-256을 확인할 수 있습니다.
- 기존 MSI 설치본은 새 MSI로 업그레이드하며 사용자 설정을 유지합니다.

## [4.11.4](https://github.com/chzzk-dev/CHZZK-Auto-Category/releases/tag/v4.11.4) — 2026-10-14 (KST)

### 변경 사항

- 새 버전을 main에 업로드하면 Windows 검증 후 MSI와 변경 기록을 GitHub Release에 자동 게시합니다.
- 자동 감지 대기 목록에 새 게임이 추가되면 알림음을 재생합니다. 같은 게임의 반복 감지와 LoL 대기실·게임 전환에는 중복 재생하지 않습니다.
- 설정에서 대기 목록 알림음을 켜거나 끌 수 있습니다. 기존 사용자도 기본으로 활성화됩니다.
- Python 앱과 Chrome 확장 소스를 저장소에서 관리하도록 연결했습니다.
- 설치 패키지를 MSI로 통일하고 전용 설치·복구·제거 UI를 추가했습니다.
- UI와 Custom Action DLL을 분리하고 설치 화면 초기화 진단을 보완했습니다.
- Windows CI에서 설치 UI 로딩과 네이티브 래퍼·MSI 빌드를 검사합니다.
- 릴리스 변경 기록을 MD 파일과 GitHub 릴리스 설명에 자동으로 남깁니다.

### 커밋

- ci: publish new MSI versions automatically after successful main builds ([565451f](https://github.com/chzzk-dev/CHZZK-Auto-Category/commit/565451f0779a7a00488483c02742dd3b33d2eac1))
- feat: play an alert once when detected games enter the pending list ([610a2c2](https://github.com/chzzk-dev/CHZZK-Auto-Category/commit/610a2c2fc8b66250ab618ff32d84d560cdd3ce6e))
- Remove outdated information from README.md ([ecde489](https://github.com/chzzk-dev/CHZZK-Auto-Category/commit/ecde489d87c49dad391cf147f1e8400eb79caea1))
- fix: read both CHZZK build credentials from Actions secrets ([f92f4a0](https://github.com/chzzk-dev/CHZZK-Auto-Category/commit/f92f4a0960ae96e6f14328f8bfa297b5f9f7285a))
- Update chzzk_open.py ([13a45da](https://github.com/chzzk-dev/CHZZK-Auto-Category/commit/13a45dac15665a738647947395e8acf55d291f1e))
- test: compare resolved native paths in Windows MSI checks ([4e58f94](https://github.com/chzzk-dev/CHZZK-Auto-Category/commit/4e58f9458a48edd51296f5c92870731055a2a575))
- feat: add 4.11.4 MSI source, Windows CI, and automatic release Markdown ([c206ab6](https://github.com/chzzk-dev/CHZZK-Auto-Category/commit/c206ab651899012c68b86e8b836e1e5482a358cb))

[전체 변경 비교](https://github.com/chzzk-dev/CHZZK-Auto-Category/compare/4.11.3...v4.11.4)

### 설치 파일

- `ChzzkAutoCategory-4.11.4.msi`
- `SHA256SUMS.txt`에서 설치 파일의 SHA-256을 확인할 수 있습니다.
- 기존 MSI 설치본은 새 MSI로 업그레이드하며 사용자 설정을 유지합니다.

## 이전 배포

저장소에 소스가 등록되기 전 배포 내역은 [GitHub Releases](https://github.com/chzzk-dev/CHZZK-Auto-Category/releases)에서 확인할 수 있습니다.
