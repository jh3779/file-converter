; File Converter — Windows 인스톨러 (Inno Setup 6+)
; 빌드: ISCC packaging\installer.iss /DMyAppVersion=<x.y.z> /DDistDir=<dist\FileConverter 절대경로>
; 로컬 수동 컴파일 시 위 두 define을 생략하면 기본값(테스트용)을 쓴다.
;
; 설계 결정(DEC-013):
;  - 관리자 권한 불요(PrivilegesRequired=lowest) — 개인 PC 사용자 대상 도구라
;    UAC 프롬프트 없이 사용자 폴더에 설치. REQ-NF-006(설명서 없이 3클릭) 정신을
;    설치 과정에도 동일하게 적용.
;  - 한국어/영어 설치 언어 — 앱 자체의 ko/en 지원(DEC-009)과 일관.
;  - 자동 업데이트 체크 없음 — REQ-NF-002(네트워크 요청 0건) 원칙, OQ-002 미결 상태 유지.
;  - 제3자 라이선스(THIRD_PARTY_NOTICES.txt)는 EULA로 강제 동의시키지 않고
;    설치 전 정보 페이지로만 보여준다 — 우리 소프트웨어가 아닌 번들 구성요소 고지이므로
;    "동의해야 진행 가능"으로 만드는 것은 부적절하다고 판단.

#ifndef MyAppVersion
  #define MyAppVersion "0.0.0-dev"
#endif
#ifndef DistDir
  #define DistDir "..\dist\FileConverter"
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
DisableProgramGroupPage=yes
DisableWelcomePage=no
OutputDir=installer-out
OutputBaseFilename=FileConverter-Setup-{#MyAppVersion}
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
; lzma2/max는 ~600MB 번들(LibreOffice 등 이미 조밀한 바이너리 다수)에서
; CI 시간 대비 압축률 이득이 작아 normal로 절충 (매 PR마다 도는 게이트라 시간 비용 고려)
Compression=lzma2/normal
SolidCompression=yes
WizardStyle=modern
InfoBeforeFile=THIRD_PARTY_NOTICES.txt

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "{#DistDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent
