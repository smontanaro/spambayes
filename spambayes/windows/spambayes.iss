;
; Inno Setup 4.x setup file for the Spambayes Binaries
;

[Setup]
AppName=Spambayes
AppVerName=Spambayes 1.0a6
AppVersion=1.0a6
DefaultDirName={pf}\Spambayes
DefaultGroupName=Spambayes
OutputDir=.
OutputBaseFilename=SpamBayes-Setup
ShowComponentSizes=no
; Note the check for Outlook running has already been done, so no point
; having this file tell them to shutdown outlook!
; Edit file using Windows 'wordpad'
;InfoBeforeFile=installation_notes.rtf
[Files]
Source: "py2exe\dist\lib\*.*"; DestDir: "{app}\lib"; Flags: ignoreversion

Source: "py2exe\dist\outlook\spambayes_addin.dll"; DestDir: "{app}\outlook"; Check: InstallingOutlook; Flags: ignoreversion regserver
Source: "py2exe\dist\outlook\docs\welcome.html"; DestDir: "{app}\outlook\docs"; Check: InstallingOutlook; Flags: isreadme
Source: "py2exe\dist\outlook\*.*"; DestDir: "{app}\outlook"; Check: InstallingOutlook; Flags: ignoreversion recursesubdirs

Source: "py2exe\dist\proxy\*.*"; DestDir: "{app}\proxy"; Check: InstallingProxy; Flags: ignoreversion recursesubdirs
Source: "py2exe\dist\proxy\readme_proxy.html"; DestDir: "{app}\proxy"; Check: InstallingProxy; Flags: isreadme

[Tasks]
Name: startup; Description: "Execute SpamBayes each time Windows starts";
Name: desktop; Description: "Add an icon to the desktop"; Flags: unchecked;

[Run]
FileName:"{app}\proxy\pop3proxy_tray.exe"; Description: "Start the server now"; Flags: postinstall skipifdoesntexist nowait

[Icons]
Name: "{group}\SpamBayes Tray Icon"; Filename: "{app}\proxy\pop3proxy_tray.exe"; Check: InstallingProxy
Name: "{userdesktop}\SpamBayes Tray Icon"; Filename: "{app}\proxy\pop3proxy_tray.exe"; Check: InstallingProxy; Tasks: desktop
Name: "{userstartup}\SpamBayes Tray Icon"; Filename: "{app}\proxy\pop3proxy_tray.exe"; Check: InstallingProxy; Tasks: startup
Name: "{group}\About SpamBayes"; Filename: "{app}\proxy\readme_proxy.html"; Check: InstallingProxy;

Name: "{group}\SpamBayes Outlook Addin\About SpamBayes"; Filename: "{app}\outlook\about.html"; Check: InstallingOutlook
Name: "{group}\SpamBayes Outlook Addin\Troubleshooting Guide"; Filename: "{app}\outlook\docs\troubleshooting.html"; Check: InstallingOutlook

[UninstallDelete]

[Code]
var
  InstallOutlook, InstallProxy: Boolean;
  WarnedNoOutlook, WarnedBoth : Boolean;

function InstallingOutlook() : Boolean;
begin
  Result := InstallOutlook;
end;
function InstallingProxy() : Boolean;
begin
  Result := InstallProxy;
end;

function IsOutlookInstalled() : Boolean;
begin
    Result := RegKeyExists( HKCU, 'Software\Microsoft\Office\Outlook');
end;

function InitializeSetup(): Boolean;
begin
    Result := true;
    while Result do begin
        if not CheckForMutexes('_outlook_mutex_') then
            break;
          Result := MsgBox(
              'You must close Outlook before SpamBayes can be installed.' + #13 + #13 +
              'Please close all Outlook Windows (using "File->Exit and Log off"' + #13 +
              'if available) and click Retry, or click Cancel to exit the installation.'+ #13 + #13 +
              'If this message persists after closing all Outlook windows, you may' + #13 +
              'need to log off from Windows, and try again.',
              mbConfirmation, MB_RETRYCANCEL) = idRetry;
    end;
    // default our install type.
    if IsOutlookInstalled() then begin
      InstallOutlook := True;
      InstallProxy := False
    end
    else begin
      InstallOutlook := False;
      InstallProxy := True;
    end;
end;

// Inno has a pretty primitive "Components/Tasks" concept that
// doesn't quite fit what we want - so we create a custom wizard page.
function PromptApplications( BackClicked: Boolean): Boolean;
var
  Next: Boolean;
  Prompts, Values: array of String;
begin

    // First open the custom wizard page
    ScriptDlgPageOpen();

    // Set some captions
    ScriptDlgPageSetCaption('Select applications to install');
    ScriptDlgPageSetSubCaption1('A number of applications are included with this package.');
    ScriptDlgPageSetSubCaption2('Select the components you wish to install.');

    SetArrayLength(Prompts, 2);
    SetArrayLength(Values, 2);
    if InstallOutlook then
      Prompts[0] := 'Microsoft Outlook Addin (Outlook appears to be installed)'
    else
      Prompts[0] := 'Microsoft Outlook Addin (Outlook does not appear to be installed)';
    Prompts[1] := 'Server/Proxy application, for all other POP based mail clients, including Outlook Express';

    while True do begin
      if InstallOutlook then Values[0] := '1' else Values[0] := '0';
      if InstallProxy then Values[1] := '1' else Values[1] := '0';
      Next:= InputOptionArray(Prompts, Values, False, False);
      if not Next then Break;
      InstallOutlook := (Values[0] = '1');
      InstallProxy := (Values[1] = '1');

      if InstallOutlook and not IsOutlookInstalled and not WarnedNoOutlook then begin
        if MsgBox(
              'Outlook appears to not be installed.' + #13 + #13 +
              'This addin only works with Microsoft Outlook 2000 and later - it' + #13 +
              'does not work with Outlook express.' + #13 + #13 +
              'If you know that Outlook is installed, you may with to continue.' + #13 + #13 +
              'Would you like to change your selection?',
              mbConfirmation, MB_YESNO) = idNo then begin
            WarnedNoOutlook := True;
            Break; // break check loop
          end;
          Continue;
      end;

      if InstallOutlook and InstallProxy and not WarnedBoth then begin
        if MsgBox(
              'You have selected to install both the Outlook Addin and the Server/Proxy Applications.' + #13 + #13 +
              'Unless you regularly use both Outlook and another mailer on the same system' + #13 +
              'you do not need both applications.' + #13 + #13 +
              'Would you like to change your selection?',
              mbConfirmation, MB_YESNO) = idNo then begin
            WarnedBoth := True;
            Break; // break check loop
          end;
        Continue
      end;

      if not InstallOutlook and not InstallProxy then begin
        MsgBox('You must select one of the applications', mbError, MB_OK);
        Continue;
      end
      // we got to here, we are OK.
      Break;
    end
    // See NextButtonClick and BackButtonClick: return True if the click should be allowed
    if not BackClicked then
      Result := Next
    else
      Result := not Next;
    // Close the wizard page. Do a FullRestore only if the click (see above) is not allowed
    ScriptDlgPageClose(not Result);
end;


function ScriptDlgPages(CurPage: Integer; BackClicked: Boolean): Boolean;
begin
  if (not BackClicked and (CurPage = wpWelcome)) or (BackClicked and (CurPage = wpSelectDir)) then begin
    // Insert a custom wizard page between two non custom pages
	Result := PromptApplications( BackClicked );
  end
  else
    Result := True;
end;

function NextButtonClick(CurPage: Integer): Boolean;
begin
  Result := ScriptDlgPages(CurPage, False);
end;

function BackButtonClick(CurPage: Integer): Boolean;
begin
  Result := ScriptDlgPages(CurPage, True);
end;

function SkipCurPage(CurPage: Integer): Boolean;
begin
  Result := (CurPage = wpSelectTasks) and (not InstallProxy);
end;
