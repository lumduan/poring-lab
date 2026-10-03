---
doc_type: design
hypothesis: null
status: GO
role: null
verdict_date: 2026-10-03
verdict_ticket: null
supersedes: null
related: []
next_action: Keep the console VDD-only; if a stream shows an empty desktop with no tray, follow "Emergency" below.
---

# Console display layout: VDD-only, and the emergency path

**Decision (Batt, 2026-10-03).** The console session's display layout is **VDD-only**: the
1440×900 virtual display (`VDD by MTT`) is the only and main display. The Samsung is almost
always off and is **not** something to preserve; a deterministic layout for the agent is the
priority. "Windows that open on a display you can't see are a hazard."

**How it is held:**
1. Sunshine `dd_configuration_option = ensure_only_display` (restored 2026-10-03 18:38, read back
   identical to the original): every stream applies VDD-only, and its revert restores the layout
   from before the stream;
2. the console's own layout was set VDD-only on 2026-10-03 17:46 (persisted with
   `CDS_UPDATEREGISTRY`), so what a stream reverts TO is VDD-only as well.

## What happened (2026-10-03, clean room V3b)

With `dd_configuration_option = disabled` (the §9a Samsung test), the console came up with the
Samsung **active and main** (`\\.\DISPLAY1`, 0,0, 1280×720 logical = 1920×1080 at 150 %) and the
VDD secondary (`\\.\DISPLAY4` at x=1920). Every window (the RO client, the agent's shell, Batt's
console) sat on the Samsung. The stream, which captures `output_name` = the VDD, showed an empty
desktop and a taskbar **without tray icons** (Windows draws those only on the main display).
That is the symptom to recognise.

## Emergency: the lab stream shows an empty desktop / no tray

**From the lab (the agent, through the mux; what was done on 2026-10-03):**
1. Click the terminal's button on the VDD taskbar (thumbnails appear: pick "poring-lab shell"),
   then `Win+Shift+Right` (or Left) to move that window onto the VDD; verify it (`open-terminal`).
2. Read the layout in a FRESH process: `powershell -NoProfile -Command "Add-Type -AssemblyName
   System.Windows.Forms; [System.Windows.Forms.Screen]::AllScreens | ft DeviceName,Primary,Bounds"`.
   ⚠️ `Screen.AllScreens` is cached per process and refreshed only by a message loop a console
   lacks: the agent's own shell returned the RDP session's display after the handover.
3. Make the VDD the only display by DEVICE NAME (not `DisplaySwitch /internal|/external`, which
   picks by heuristics both monitors fail), with a 240 s dead-man that runs `DisplaySwitch /extend`
   unless `%TEMP%\pl-vdd-ok` appears. Substitute the names from step 2 (VDD = 1440×900):

       cls; Remove-Item "$env:TEMP\pl-vdd-ok" -EA 0; Start-Process powershell -WindowStyle Hidden -ArgumentList '-NoProfile -Command "Start-Sleep 240; if (-not (Test-Path $env:TEMP\pl-vdd-ok)) { DisplaySwitch.exe /extend }"'; Add-Type -TypeDefinition 'using System;using System.Runtime.InteropServices;public class PlDisp2{[StructLayout(LayoutKind.Sequential,CharSet=CharSet.Ansi)]public struct DM{[MarshalAs(UnmanagedType.ByValTStr,SizeConst=32)]public string Name;public short SpecV;public short DrvV;public short Size;public short Extra;public int Fields;public int X;public int Y;public int Orient;public int Fixed;public short Color;public short Duplex;public short YRes;public short TT;public short Collate;[MarshalAs(UnmanagedType.ByValTStr,SizeConst=32)]public string Form;public short LogPx;public int Bpp;public int W;public int H;public int DFlags;public int Freq;public int R1;public int R2;public int R3;public int R4;public int R5;public int R6;public int R7;public int R8;}[DllImport("user32.dll",CharSet=CharSet.Ansi)]public static extern bool EnumDisplaySettings(string n,int m,ref DM d);[DllImport("user32.dll",CharSet=CharSet.Ansi)]public static extern int ChangeDisplaySettingsEx(string n,ref DM d,IntPtr w,uint f,IntPtr l);[DllImport("user32.dll")]public static extern int ChangeDisplaySettingsEx(IntPtr n,IntPtr d,IntPtr w,uint f,IntPtr l);}' -EA 0; $v = New-Object PlDisp2+DM; $v.Size = [Runtime.InteropServices.Marshal]::SizeOf($v); [void][PlDisp2]::EnumDisplaySettings('\\.\DISPLAY4', -1, [ref]$v); $v.X = 0; $v.Y = 0; $v.Fields = $v.Fields -bor 0x20; $s = New-Object PlDisp2+DM; $s.Size = $v.Size; [void][PlDisp2]::EnumDisplaySettings('\\.\DISPLAY1', -1, [ref]$s); $s.W = 0; $s.H = 0; $s.Fields = 0x20 -bor 0x80000 -bor 0x100000; 'vdd ' + $v.W + 'x' + $v.H + ' primary: ' + [PlDisp2]::ChangeDisplaySettingsEx('\\.\DISPLAY4', [ref]$v, [IntPtr]::Zero, 0x10000011, [IntPtr]::Zero); 'samsung detach: ' + [PlDisp2]::ChangeDisplaySettingsEx('\\.\DISPLAY1', [ref]$s, [IntPtr]::Zero, 0x10000001, [IntPtr]::Zero); 'apply: ' + [PlDisp2]::ChangeDisplaySettingsEx([IntPtr]::Zero, [IntPtr]::Zero, [IntPtr]::Zero, 0, [IntPtr]::Zero)

   It prints `vdd 1440x900 primary: 0`, `samsung detach: 0`, `apply: 0` (0 = success). Within 240 s:
   `New-Item "$env:TEMP\pl-vdd-ok" -Force`, then repeat step 2: one display, primary, 0,0, 1440×900.
   ⚠️ PowerShell is case-insensitive: two struct fields differing only by case (`h`/`H`) break
   every property access (attempt 1). A 60 s dead-man was too short for paced typing (attempt 2).
4. The RO client re-sizes itself to fill the VDD when a display disappears: paced Alt+F4,
   relaunch from the shortcut (it opens with its client at 8,31), drag the title (400,15) →
   (472,61), then the 1 px correction (400,62) → (400,40) → (400,61); `client_title_active` and
   `service_select` must match before the login.

**At the rack (a human, the Samsung on):**
- Settings → System → Display: select the 1440×900 display → "Make this my main display"; then
  select the Samsung → "Disconnect this display". Or `Win+P` → **Second screen only** when the
  Samsung is the main display (it keeps the non-main display, the VDD) -- check the result.

**At the rack, blind (nothing visible, keyboard only):** `Win+P` opens the Project list (PC screen
only, Duplicate, Extend, Second screen only). Press `Down` four times (it stops at the last
item, **Second screen only**), then `Enter`. If the lab stream still shows no desktop after
~10 s, `Win+P`, `Up` four times (**PC screen only**), `Enter`. One of the two keeps the VDD; the
lab stream showing the desktop WITH tray icons is the check. (Not yet tried blind: written from the
list order.)

**Never:** `Win+P` through RDP (it changes the RDP session's projection, not the console's).
