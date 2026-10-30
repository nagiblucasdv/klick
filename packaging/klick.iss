; Instalador do Klick (Inno Setup 6). Rode pelo packaging\build.ps1, que passa a versão e
; monta dist\Klick antes. Instala só para o usuário atual: não pede administrador.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#define AppName "Klick"
#define AppExe "Klick.exe"

[Setup]
; Não mude o AppId: é por ele que o Windows reconhece atualizações e a desinstalação.
AppId={{DA664061-8E4B-40AB-8701-86AF829DCF59}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Lucas Nagib
AppCopyright=Criado por Lucas Nagib
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\dist
OutputBaseFilename=Klick-Setup-{#AppVersion}
SetupIconFile=..\build\klick.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=no

[Languages]
Name: "ptbr"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[CustomMessages]
ptbr.TaskStartup=Iniciar o Klick junto com o Windows
ptbr.TaskPrintScreen=Usar a tecla PrintScreen para o Klick (tira ela da Ferramenta de Captura do Windows)
ptbr.TaskPrintScreenGroup=Atalho:
ptbr.RunKlick=Abrir o Klick agora
ptbr.DeleteData=Apagar também o histórico de capturas e as preferências do Klick?%n%nAs imagens que você salvou em outras pastas não são apagadas.

[Tasks]
Name: "startup"; Description: "{cm:TaskStartup}"
Name: "printscreen"; Description: "{cm:TaskPrintScreen}"; GroupDescription: "{cm:TaskPrintScreenGroup}"
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\Klick\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\build\ffmpeg\ffmpeg.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\build\ffmpeg\LICENSE"; DestDir: "{app}\licenses"; DestName: "ffmpeg-LICENSE.txt"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autoprograms}\{#AppName} - Histórico"; Filename: "{app}\{#AppExe}"; Parameters: "--history"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "{#AppName}"; \
  ValueData: """{app}\{#AppExe}"" --startup"; Tasks: startup; Flags: uninsdeletevalue
; Sem isso o Windows 11 abre a Ferramenta de Captura junto com o Klick. Desinstalar devolve o padrão.
Root: HKCU; Subkey: "Control Panel\Keyboard"; ValueType: dword; ValueName: "PrintScreenKeyForSnippingEnabled"; \
  ValueData: 0; Tasks: printscreen; Flags: uninsdeletevalue

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:RunKlick}"; Flags: nowait postinstall skipifsilent

[Code]
// O Klick fica na bandeja, sem janela para receber "fechar"; encerra o processo para poder substituir os arquivos.
procedure StopKlick();
var
  Code: Integer;
begin
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM {#AppExe}', '', SW_HIDE, ewWaitUntilTerminated, Code);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  StopKlick();
  Result := '';
end;

function InitializeUninstall(): Boolean;
begin
  StopKlick();
  Result := True;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if (CurUninstallStep = usPostUninstall) and not UninstallSilent() then
    if MsgBox(CustomMessage('DeleteData'), mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
    begin
      DelTree(ExpandConstant('{localappdata}\Klick'), True, True, True);
      RegDeleteKeyIncludingSubkeys(HKCU, 'Software\Klick');
    end;
end;
