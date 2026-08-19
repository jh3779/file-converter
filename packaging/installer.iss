; File Converter — Windows 인스톨러 (Inno Setup 6+)
; 빌드(전체 설치 파일): ISCC packaging\installer.iss /DMyAppVersion=<x.y.z> /DDistDir=<dist\FileConverter 절대경로>
; 빌드(앱만 업데이트 설치 파일, DEC-062): 위 두 define에 더해 /DAppOnly=1 /DEngineHash=<12자리 16진수>
; 로컬 수동 컴파일 시 define들을 생략하면 기본값(테스트용)을 쓴다.
;
; 설계 결정(DEC-013):
;  - 관리자 권한 불요(PrivilegesRequired=lowest) — 개인 PC 사용자 대상 도구라
;    UAC 프롬프트 없이 사용자 폴더에 설치. REQ-NF-006(설명서 없이 3클릭) 정신을
;    설치 과정에도 동일하게 적용.
;  - 한국어/영어 설치 언어 — 앱 자체의 ko/en 지원(DEC-009)과 일관.
;  - 업데이트: 옵트인 확인(DEC-022)에 이어, 엔진(JRE·LibreOffice·FFmpeg)과 앱
;    코드를 분리한 다운로드·자동 설치까지 지원(DEC-062) — 여전히 사용자가
;    "지금 업데이트"를 직접 눌러야만 네트워크를 탄다(REQ-NF-002 원칙 유지).
;  - 제3자 라이선스(THIRD_PARTY_NOTICES.txt)는 EULA로 강제 동의시키지 않고
;    설치 전 정보 페이지로만 보여준다 — 우리 소프트웨어가 아닌 번들 구성요소 고지이므로
;    "동의해야 진행 가능"으로 만드는 것은 부적절하다고 판단.

#ifndef MyAppVersion
  #define MyAppVersion "0.0.0-dev"
#endif
#ifndef DistDir
  #define DistDir "..\dist\FileConverter"
#endif
#ifndef EngineHash
  #define EngineHash "dev"
#endif

; AppOnly(DEC-062): 앱 코드만 담은 "업데이트" 설치 파일 — 릴리스마다 거의
; 안 바뀌는 engine\(JRE·LibreOffice·FFmpeg, 수백MB)을 빼고 훨씬 작은 다운로드를
; 만든다. 같은 AppId·설치 경로를 그대로 써서 기존 설치 위에 앱 파일만 덮어쓴다
; (engine\은 손대지 않으므로 이전 전체 설치가 깔아둔 그대로 남는다).
#ifdef AppOnly
  #define OutputBaseFilenameValue "FileConverter-Update-" + MyAppVersion + "-engine-" + EngineHash
#else
  #define OutputBaseFilenameValue "FileConverter-Setup-" + MyAppVersion
#endif

#define MyAppName "File Converter"
#define MyAppNameKo "파일 변환기"
#define MyAppPublisher "file-converter project"
#define MyAppURL "https://github.com/jh3779/file-converter"
#define MyAppExeName "FileConverter.exe"

[Setup]
; 고정 GUID — 절대 변경 금지(버전 업그레이드 시 동일 앱으로 인식되는 근거)
AppId={{BA9BB41E-3B10-4971-9EDD-2DC914242EBF}
AppName={#MyAppName} ({#MyAppNameKo})
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
VersionInfoVersion={#MyAppVersion}
DefaultDirName={autopf}\FileConverter
DefaultGroupName=File Converter
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
; 번들 바이너리(FileConverter.exe·엔진 전부)가 전량 64비트라 32비트 Windows에서는
; 애초에 실행이 불가능하다 — 설치만 되고 실행이 실패하는 상황을 막기 위해 아예 차단한다.
; ArchitecturesInstallIn64BitMode가 없으면 Inno Setup은 32비트 설치 모드로 동작해
; {autopf}가 "모든 사용자용으로 설치" 선택 시 {commonpf32}(Program Files (x86))로
; 해석되는 버그가 있었다(실사용 QA 리포트 #48) — 지정해 64비트 Program Files로 고정.
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
DisableProgramGroupPage=yes
DisableWelcomePage=no
OutputDir=installer-out
OutputBaseFilename={#OutputBaseFilenameValue}
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
; lzma2/max는 ~600MB 번들(LibreOffice 등 이미 조밀한 바이너리 다수)에서
; CI 시간 대비 압축률 이득이 작아 normal로 절충 (매 PR마다 도는 게이트라 시간 비용 고려)
Compression=lzma2/normal
SolidCompression=yes
WizardStyle=modern
InfoBeforeFile=THIRD_PARTY_NOTICES.txt
; DEC-062: "지금 업데이트"가 다운로드한 설치 파일을 무인(/VERYSILENT)으로
; 실행할 때, 아직 완전히 종료되지 않은 실행 중인 FileConverter.exe가 설치
; 대상 파일을 잠그고 있을 수 있다. CloseApplications=force는 Restart Manager로
; 그 잠금을 쥔 프로세스를 대화상자 없이 자동으로 종료시킨다(AppMutex는 대화상자
; 기반이라 무인 설치에서는 효과가 없어 채택하지 않음). RestartApplications=no —
; 무인 설치 중 앱을 임의로 다시 띄우지 않는다(대화식 설치는 아래 [Run]이 처리).
CloseApplications=force
RestartApplications=no

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
#ifdef AppOnly
; engine\(JRE·LibreOffice·FFmpeg)은 제외 — 이미 설치돼 있는 그대로 둔다.
; "\engine"(백슬래시 있음, 와일드카드 없음)은 {#DistDir} 기준 상대경로
; "engine" 디렉터리 자체를 제외한다는 뜻 — 이러면 그 하위 파일들뿐 아니라
; createallsubdirs가 만들 빈 engine\ 폴더 자체도 안 만들어진다. "\engine\*"
; 처럼 와일드카드를 붙이면 파일은 빠져도 빈 engine\ 폴더가 남는다.
Source: "{#DistDir}\*"; DestDir: "{app}"; Excludes: "\engine"; Flags: ignoreversion recursesubdirs createallsubdirs
#else
Source: "{#DistDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
#endif

[UninstallDelete]
; DEC-062: Inno Setup 언인스톨러는 "가장 최근 설치 실행이 기록한 로그"만
; 지운다 — 전체 설치(engine\ 포함 로그) 후 나중에 앱만 설치(engine\ 미포함
; 로그)하면, 그 다음 제거 시 로그에 없는 engine\이 수백MB 그대로 남는다
; (REQ-NF-003 "깨끗이 지워짐" 위반). AppOnly 여부와 무관하게 항상 이 항목을
; 두면, 실행 로그가 뭘 담았든 제거 시 engine\을 명시적으로 지운다.
Type: filesandordirs; Name: "{app}\engine"

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent
