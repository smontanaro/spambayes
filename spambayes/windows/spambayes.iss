;
; Inno Setup 5.x setup file for the SpamBayes Binaries
;

[Setup]
; Version specific constants
AppVerName=SpamBayes 1.1a6
AppVersion=1.1a6
OutputBaseFilename=spambayes-1.1a6
; Normal constants.  Be careful about changing 'AppName'
AppName=SpamBayes
DefaultDirName={pf}\SpamBayes
DefaultGroupName=SpamBayes
OutputDir=.
ShowComponentSizes=no
UninstallDisplayIcon={app}\sbicon.ico
LicenseFile=py2exe\dist\license.txt
PrivilegesRequired=admin

[Files]
Source: "py2exe\dist\sbicon.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "py2exe\dist\LICENSE.txt"; DestDir: "{app}"; Flags: ignoreversion

Source: "py2exe\dist\lib\*.*"; DestDir: "{app}\lib"; Flags: ignoreversion
Source: "py2exe\dist\bin\python25.dll"; DestDir: "{app}\bin"; Flags: ignoreversion
; Needed when built with Python 2.4/2.5.  This must be manually copied to this directory
; from wherever it is being sourced from.
Source: "py2exe\dist\bin\msvcr71.dll"; DestDir: "{app}\bin"; Flags: ignoreversion

; Is there a cleverer way of including all of these?
Source: "py2exe\dist\languages\es\LC_MESSAGES\*.mo"; DestDir: "{app}\languages\DIALOGS\es"; Flags: ignoreversion
Source: "py2exe\dist\languages\es_AR\LC_MESSAGES\*.mo"; DestDir: "{app}\languages\DIALOGS\es_AR"; Flags: ignoreversion

Source: "py2exe\dist\bin\outlook_addin.dll"; DestDir: "{app}\bin"; Check: InstallingOutlook; Flags: ignoreversion
Source: "py2exe\dist\bin\outlook_addin_register.exe"; DestDir: "{app}\bin"; Check: InstallingOutlook; Flags: ignoreversion
Source: "py2exe\dist\bin\outlook_dump_props.exe"; DestDir: "{app}\bin"; Check: InstallingOutlook; Flags: ignoreversion
Source: "py2exe\dist\docs\outlook\*.*"; DestDir: "{app}\docs\outlook"; Check: InstallingOutlook; Flags: ignoreversion recursesubdirs
Source: "py2exe\dist\docs\outlook\docs\welcome.html"; DestDir: "{app}\docs\outlook\docs"; Check: InstallingOutlook; Flags: isreadme
Source: "py2exe\dist\bin\default_bayes_customize.ini"; DestDir: "{app}\bin"; Check: InstallingOutlook; Flags: ignoreversion

Source: "py2exe\dist\bin\sb_server.exe"; DestDir: "{app}\bin"; Check: InstallingProxy; Flags: ignoreversion
Source: "py2exe\dist\bin\sb_service.exe"; DestDir: "{app}\bin"; Check: InstallingProxy; Flags: ignoreversion
Source: "py2exe\dist\bin\sb_pop3dnd.exe"; DestDir: "{app}\bin"; Check: InstallingProxy; Flags: ignoreversion
Source: "py2exe\dist\bin\sb_tray.exe"; DestDir: "{app}\bin"; Check: InstallingProxy; Flags: ignoreversion
Source: "py2exe\dist\bin\sb_upload.exe"; DestDir: "{app}\bin"; Check: InstallingProxy; Flags: ignoreversion
Source: "py2exe\dist\bin\setup_server.exe"; DestDir: "{app}\bin"; Check: InstallingProxy; Flags: ignoreversion
Source: "py2exe\dist\docs\sb_server\readme_proxy.html"; DestDir: "{app}\docs\sb_server"; Check: InstallingProxy; Flags: isreadme
Source: "py2exe\dist\docs\sb_server\troubleshooting.html"; DestDir: "{app}\docs\sb_server"; Check: InstallingProxy
Source: "py2exe\dist\docs\sb_server\*.*"; DestDir: "{app}\docs\sb_server"; Check: InstallingProxy; Flags: recursesubdirs

Source: "py2exe\dist\bin\sb_imapfilter.exe"; DestDir: "{app}\bin"; Check: InstallingIMAP; Flags: ignoreversion

Source: "py2exe\dist\bin\convert_database.exe"; DestDir: "{app}\bin"; Flags: ignoreversion

; Include flavour-of-the-day OCR pacakge - currently gocr.
; Get from the spambayes package directory - its likely to exist
; there as the developer running a source version will have it there.
Source: "..\..\spambayes\gocr.exe"; DestDir: "{app}\bin"; Flags: ignoreversion
Source: "py2exe\gocr.txt"; DestDir: "{app}\docs"; Flags: ignoreversion

; There is a problem attempting to get Inno to unregister our DLL.  If we mark our DLL
; as 'regserver', it installs and registers OK, but at uninstall time, it unregisters
; OK, but Inno is then unable to delete the files.  My guess is Inno loads the DLL,
; calls the function, and unloads the library.  For our executables, this process
; will leave many files in use.
; We get around this by having a little executable purely for registration and
; unregistration.
[Run]
Filename: "{app}\bin\outlook_addin_register.exe"; StatusMsg: "Registering Outlook Addin"; Check: InstallingOutlook;
; Possibly register for all users (unregister removes this if it is present, so we don't need
; a special case for that). We do both a single-user registration and then the all-user, because
; that keeps the script much simpler, and it doesn't do any harm.
Filename: "{app}\bin\outlook_addin_register.exe"; Parameters: "HKEY_LOCAL_MACHINE"; StatusMsg: "Registering Outlook Addin for all users"; Check: InstallOutlookAllUsers;
[UninstallRun]
Filename: "{app}\bin\outlook_addin_register.exe"; Parameters: "--unregister"; StatusMsg: "Unregistering Outlook Addin"; Check: InstallingOutlook;

[Run]
FileName:"{app}\bin\convert_database.exe"; Description: "Convert the database from 1.0 to 1.1"; Flags: postinstall skipifdoesntexist; Check: ConvertDatabase
FileName:"{app}\bin\sb_tray.exe"; Description: "Start the server now"; Flags: postinstall skipifdoesntexist nowait; Check: InstallingProxy

[Icons]
Name: "{group}\SpamBayes Tray Icon"; Filename: "{app}\bin\sb_tray.exe"; Check: InstallingProxy;
Name: "{userdesktop}\SpamBayes Tray Icon"; Filename: "{app}\bin\sb_tray.exe"; Check: DesktopIcon;
Name: "{userstartup}\SpamBayes Tray Icon"; Filename: "{app}\bin\sb_tray.exe"; Check: StartupProxy;
Name: "{group}\About SpamBayes"; Filename: "{app}\docs\sb_server\readme_proxy.html"; Check: InstallingProxy;
Name: "{group}\Troubleshooting Guide"; Filename: "{app}\docs\sb_server\troubleshooting.html"; Check: InstallingProxy;

Name: "{group}\SpamBayes IMAP Filter Web Interface"; Filename: "{app}\sb_imapfilter.exe"; Parameters: "-b"; Check: InstallingIMAP;
Name: "{userstartup}\SpamBayes IMAP Filter"; Filename: "{app}\bin\sb_imapfilter.exe"; Parameters: "-c -t -l 10"; Check: StartupIMAP;

Name: "{group}\SpamBayes Outlook Addin\About SpamBayes"; Filename: "{app}\docs\outlook\about.html"; Check: InstallingOutlook;
Name: "{group}\SpamBayes Outlook Addin\Troubleshooting Guide"; Filename: "{app}\docs\outlook\docs\troubleshooting.html"; Check: InstallingOutlook;

[UninstallDelete]

[Code]
var
  InstallOutlook, InstallProxy, InstallIMAP: Boolean;
  WarnedNoOutlook, WarnedBoth : Boolean;
  startup, desktop, allusers, startup_imap, convert_db : Boolean; // Tasks

function InstallingOutlook() : Boolean;
begin
  Result := InstallOutlook;
end;
function InstallingProxy() : Boolean;
begin
  Result := InstallProxy;
end;
function InstallingIMAP() : Boolean;
begin
  Result := InstallIMAP;
end;

function StartupProxy() : Boolean;
begin
  Result := startup;
end;
function DesktopIcon() : Boolean;
begin
  Result := desktop;
end;
function InstallOutlookAllUsers() : Boolean;
begin
  Result := allusers;
end;
function StartupIMAP() : Boolean;
begin
  Result := startup_imap;
end;
function ConvertDatabase() : Boolean;
begin
  Result := convert_db;
end;

function IsOutlookInstalled() : Boolean;
begin
    Result := RegKeyExists( HKCU, 'Software\Microsoft\Office\Outlook');
end;

function CheckNoAppMutex( mutexName: String; closeMsg: String) : Boolean;
begin
    Result := true;
    while Result do begin
        if not CheckForMutexes(mutexName) then
            break;
        Result := MsgBox(closeMsg, mbConfirmation, MB_RETRYCANCEL) = idRetry;
    end;
end;

function InitializeSetup(): Boolean;
var
  closeit: String;
begin
    // Check if Outlook is running.
    closeit:= 'You must close Outlook before SpamBayes can be installed.' + #13 + #13 +
              'Please close all Outlook Windows (using "File->Exit and Log off"' + #13 +
              'if available) and click Retry, or click Cancel to exit the installation.'+ #13 + #13 +
              'If this message persists after closing all Outlook windows, you may' + #13 +
              'need to log off from Windows, and try again.'
    Result := CheckNoAppMutex('_outlook_mutex_', closeit);
    // Check if MAPISP32.EXE is running - if it is, it implies something is screwey
    // with Outlook.
    if Result then begin
      closeit := 'The Outlook mail delivery agent is still running.' + #13 + #13 +
                 'If you only recently closed Outlook, wait a few seconds and click Retry.' + #13 + #13 +
                 'If this message persists, you may need to log off from Windows, and try again.'
      Result := CheckNoAppMutex('InternetMailTransport', closeit);
    end;
    // And finally, the SpamBayes server
    if Result then begin
      // Tell them to 'Stop' then 'Exit', so any services are also stopped
      closeit:= 'An existing SpamBayes server is already running.' + #13 + #13 +
                'Please shutdown this server before installing.  If the SpamBayes tray icon' + #13 +
                'is running, Right-click it and select "Exit SpamBayes".' + #13 +
                'If the Windows Service version of SpamBayes is running, please stop' + #13 +
                'it via "Control Panel->Administrative Tools->Services".' + #13 + #13
                'If this message persists, you may need to restart Windows.'
      Result := CheckNoAppMutex('SpamBayesServer', closeit);
    end;

    // default our install type.
    if IsOutlookInstalled() then begin
      InstallOutlook := True;
      InstallProxy := False;
      InstallIMAP := False;
    end
    else begin
      InstallOutlook := False;
      InstallProxy := True;
      InstallIMAP := False;
    end;
    startup := False;
    desktop := False;
    allusers := False;
    startup_imap := False;
    convert_db := False;
end;

// Inno has a pretty primitive "Components/Tasks" concept that
// doesn't quite fit what we want - so we create custom wizard pages.

var
  ComponentsPage: TInputOptionWizardPage;
  TasksPage: TInputOptionWizardPage;

procedure InitializeWizard;
begin
  { Create the Components page }

  ComponentsPage := CreateInputOptionPage(wpWelcome,
    'Select applications to install',
    'A number of applications are included with this package.',
    'Select the components you wish to install, then click Next.',
    False, False);
  if InstallOutlook then
    ComponentsPage.Add('Microsoft Outlook Addin (Outlook appears to be installed)')
  else
    ComponentsPage.Add('Microsoft Outlook Addin (Outlook does not appear to be installed)');
  ComponentsPage.Add('Server/Proxy Application, for all other POP based mail clients, including Outlook Express');
  ComponentsPage.Add('IMAP Filter Application, for all other IMAP based mail clients');

  { Set default values based on whether or not Outlook is installed. }

  if InstallOutlook then ComponentsPage.Values[0] := True else ComponentsPage.Values[0] := False;
  if InstallProxy then ComponentsPage.Values[1] := True else ComponentsPage.Values[1] := False;
  if InstallIMAP then ComponentsPage.Values[2] := True else ComponentsPage.Values[2] := False;

  { Create the Tasks page.  Note that this is empty and gets replaced later. }
  TasksPage := CreateInputOptionPage(ComponentsPage.ID,
    'Select additional tasks',
    'Which additional tasks should be performed?',
    'Select the components you would like Setup to perform while installing SpamBayes, then click Next.',
    False, False);
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  I: Integer;
begin
  { Validate certain pages before allowing the user to proceed }
  if CurPageID = TasksPage.ID then begin
    convert_db := TasksPage.Values[0];
    I := 1;
    if InstallOutlook then begin
      allusers := TasksPage.Values[I];
      I := I + 1;
    end;
    if InstallProxy then begin
      startup := TasksPage.Values[I];
      desktop := TasksPage.Values[I+1];
      I := I + 2;
    end;
    if InstallIMAP then begin
      startup_imap := TasksPage.Values[I];
      I := I + 1;
    end;
  end;
  if CurPageID = ComponentsPage.ID then begin
    InstallOutlook := ComponentsPage.Values[0];
    InstallProxy := ComponentsPage.Values[1];
    InstallIMAP := ComponentsPage.Values[2];

    if InstallOutlook and not IsOutlookInstalled and not WarnedNoOutlook then begin
      if MsgBox(
            'Outlook does not appear to be installed.' + #13 + #13 +
            'This addin only works with Microsoft Outlook 2000 and later - it' + #13 +
            'does not work with Outlook Express.' + #13 + #13 +
            'If you know that Outlook is installed, you may wish to continue.' + #13 + #13 +
            'Would you like to change your selection?',
            mbConfirmation, MB_YESNO) = idNo then begin
        WarnedNoOutlook := True;
        Result := True;
      end else
        Result := False;
    end else if InstallOutlook and (InstallProxy or InstallIMAP) and not WarnedBoth then begin
      if MsgBox(
            'You have selected to install both the Outlook Addin and the Server/Proxy/IMAP Applications.' + #13 + #13 +
            'Unless you regularly use both Outlook and another mailer on the same system,' + #13 +
            'you do not need both applications.' + #13 + #13 +
            'Would you like to change your selection?',
            mbConfirmation, MB_YESNO) = idNo then begin
        WarnedBoth := True;
        Result := True;
      end else
        Result := False;
    end else if not InstallOutlook and not InstallProxy and not InstallIMAP then begin
      MsgBox('You must select one of the applications.', mbError, MB_OK);
      Result := False;
    end else
      // we got to here, we are OK.
      Result := True;

    // Generate the Tasks page based on the component selections.
    TasksPage.Free();
    TasksPage := CreateInputOptionPage(ComponentsPage.ID,
      'Select additional tasks',
      'Which additional tasks should be performed?',
      'Select the components you would like Setup to perform while installing SpamBayes, then click Next.',
      False, False);
    TasksPage.Add('Convert 1.0 database to 1.1 format');
    TasksPage.Values[0] := True;
    if InstallOutlook then
      TasksPage.Add('Register add-in for all users');
    if InstallProxy then begin
      TasksPage.Add('Execute SpamBayes each time Windows starts');
      TasksPage.Add('Add an icon to the desktop');
    end;
    if InstallIMAP then
      TasksPage.Add('Automatically execute IMAP filter periodically');
    end else
      Result := True;
end;

function UpdateReadyMemo(Space, NewLine, MemoUserInfoInfo, MemoDirInfo, MemoTypeInfo,
  MemoComponentsInfo, MemoGroupInfo, MemoTasksInfo: String): String;
var
  S: String;
begin
  { Fill the 'Ready Memo' with the normal settings and the custom settings }
  S := 'Selected applications:' + NewLine;
  if InstallOutlook then S := S + Space + 'Outlook Addin' + NewLine
  if InstallProxy then S := S + Space + 'Server/Proxy Application' + NewLine
  if InstallIMAP then S := S + Space + 'IMAP Filter Application' + NewLine
  S := S + NewLine;
  
  S := S + MemoDirInfo + NewLine + NewLine;
  S := S + MemoGroupInfo + NewLine + NewLine;

  S := S + 'Additional Tasks:' + NewLine;
  if convert_db then S := S + Space + 'Convert database from 1.0 to 1.1 format' + NewLine
  if startup then S := S + Space + 'Run Proxy on Startup' + NewLine
  if desktop then S := S + Space + 'Install Proxy Desktop Icon' + NewLine
  if allusers then S := S + Space + 'Install Addin for all users' + NewLine
  if startup_imap then S := S + Space + 'Automatically run Filter' + NewLine

  Result := S;
end;

