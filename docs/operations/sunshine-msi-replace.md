---
doc_type: design
hypothesis: null
status: PROPOSED
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: []
next_action: Batt reviews these exact steps (2026-10-02). Nothing is uninstalled before his go. Then phases A-D, with Batt opening the elevated console and approving UAC.
---

# Replacing the unsigned April Sunshine with the signature-verified v2026.914 MSI

**Why (Batt, 2026-10-02).** The running Sunshine 2025.924.154138 is an April 2026 EXE install with an
unsigned `sunshine.exe`. The signature-checked MSI was downloaded but never ran (ADR-0009). Replace it
**before** S2 step 0.

**Already verified (read-only, 2026-10-02 21:10–21:12):**
- `C:\Users\poring-lab\Downloads\Sunshine-Windows-AMD64-installer.msi`: 33,710,080 B, SHA-256
  `1d7fed8beecd5889dc7ff14cf9f42d6d38f37c3066c13c6c2a5f4e91847e0ccf`, equal to GitHub's asset digest
  for tag v2026.914.233613.
  - Authenticode **Valid**, signer `CN=David Lane` (LizardByte's maintainer).
  - MSI `ProductVersion` 2026.914.233613.
  - Features: application, core, assets, autostart, **firewall** (its own any-address rules),
    scripts, audio, tools, dxgi. No gamepad component.
- `config\` holds (every file is kept):
  - `sunshine.conf` (the VDD settings);
  - `apps.json`;
  - `sunshine_state.json`: the web-UI login and the **one paired client, poring-lab-gamestream**;
  - `display_device.state`: the **pending Samsung revert**;
  - `credentials\cacert.pem` + `cakey.pem`: **the server identity our pairing is pinned to**.

**Who.**
- Batt opens an elevated PowerShell on the Dell and approves UAC; the agent types ONLY the
  commands below, in order.
- Batt closes the elevated console at the end.
- The lab stays in RDP mode throughout. Sunshine isn't streaming, so nothing visible changes for
  the RO client.

## A. Preflight (the agent, poring-lab's console, read-only; needs ASSIST)

1. Re-check the MSI's SHA-256 and signature (as above).
2. Record:
   - the ACL of `config\credentials\cakey.pem`, and whether poring-lab (a standard user) can read
     it. If it can, that is a finding: the MSI install should restrict it, and D checks;
   - the service state and start mode;
   - the firewall rules named `Sunshine` / `sunshine.exe`, with their program paths and remote
     addresses.
3. sha256 of every file in `config\` (the reference for the restore in C), and that
   `C:\Program Files\Sunshine\scripts\install-service.bat` exists (the rollback needs it).

## B. Back up, then uninstall the EXE version (Batt's elevated console)

    $b = 'C:\ProgramData\PoringLab\sunshine-backup-20261002'
    Stop-Service SunshineService
    New-Item -ItemType Directory $b | Out-Null
    Copy-Item 'C:\Program Files\Sunshine\config' "$b\config" -Recurse
    Copy-Item 'C:\Program Files\Sunshine' "$b\program-files-sunshine" -Recurse
    icacls $b /inheritance:r /grant:r 'Administrators:(OI)(CI)F' 'SYSTEM:(OI)(CI)F' | Out-Null
    Get-ChildItem "$b\config" -Recurse -File | Get-FileHash | ft Hash,Path -AutoSize
    netsh advfirewall firewall show rule name=Sunshine verbose > "$b\firewall-before.txt"
    Start-Process 'C:\Program Files\Sunshine\uninstall.exe' -ArgumentList '/S' -Wait
    Get-Service SunshineService -EA 0; Test-Path 'C:\Program Files\Sunshine\sunshine.exe'

**Notes on B:**
- **The backup is admin-only.** It holds the server private key and the pairing state, so it never
  goes anywhere a standard user can read it.
- **The full program folder is copied too.** The April EXE installer is gone, so this copy is the
  only rollback.
- **Expected end state:** no `SunshineService`, no `sunshine.exe`.
  - `uninstall.exe /S` is the NSIS silent uninstall. It also deletes the firewall rules named
    `Sunshine`, including our 192.168.1.13 restriction, which is recreated in C.
  - If it leaves `config\`, that is fine: it is restored from `$b` anyway.

## C. Install the MSI, restore config, re-restrict the firewall (same elevated console)

    $m = 'C:\Users\poring-lab\Downloads\Sunshine-Windows-AMD64-installer.msi'
    (Get-FileHash $m).Hash -eq '1D7FED8BEECD5889DC7FF14CF9F42D6D38F37C3066C13C6C2A5F4E91847E0CCF'
    Start-Process msiexec.exe -Wait -ArgumentList '/i', "`"$m`"", '/qb', '/l*v', "`"$b\msi-install.log`""
    Stop-Service SunshineService
    Copy-Item "$b\config\*" 'C:\Program Files\Sunshine\config\' -Recurse -Force
    Get-ChildItem 'C:\Program Files\Sunshine\config' -Recurse -File | Get-FileHash | ft Hash,Path -AutoSize
    Get-NetFirewallRule | ? { ($_ | Get-NetFirewallApplicationFilter).Program -like '*\Sunshine\sunshine.exe' } |
      Set-NetFirewallRule -RemoteAddress 192.168.1.13
    Start-Service SunshineService
    Get-NetFirewallRule | ? { ($_ | Get-NetFirewallApplicationFilter).Program -like '*\Sunshine\sunshine.exe' } |
      % { '{0} {1} {2}' -f $_.DisplayName, $_.Enabled, (($_ | Get-NetFirewallAddressFilter).RemoteAddress -join ',') }

**Notes on C:**
- **The install is default** (`/qb`: a progress bar, no choices), logged to the backup folder.
- **The restore runs with the service stopped,** so the MSI's fresh state can't overwrite it. The
  restored hashes must equal A3's.
- **The firewall:** every rule bound to the new `sunshine.exe` is set to `RemoteAddress
  192.168.1.13` (CLAUDE.md rule 2), then read back.

Batt closes the elevated console.

## D. Verify (the agent; read-only on Windows plus the lab side)

| # | Check | Pass |
|---|---|---|
| 1 | Uninstall registry | one `Sunshine` entry, an MSI `{GUID}` key, DisplayVersion 2026.914.233613; the April entry gone |
| 2 | `Get-AuthenticodeSignature 'C:\Program Files\Sunshine\sunshine.exe'` | **Valid**, `CN=David Lane` |
| 3 | `sunshine.log` | "Sunshine version: 2026.914…"; config `output_name` = the VDD, `ensure_only_display`; display devices listed; "Trying to revert … false" retries resume (the pending revert survived) |
| 4 | Pairing | `sunshine_state.json` names exactly one client, `poring-lab-gamestream`. A lab-side `moonlight list` on gamestream's private display returns the app list (it only works paired) |
| 5 | Firewall | only `RemoteAddress 192.168.1.13` on the enabled Sunshine rules |
| 6 | The credentials ACL | the A2 result compared; report if a standard user can still read `cakey.pem` |
| 7 | Service | Running, Automatic |

## Rollback

- **If the MSI install fails, or D fails in a way that can't be fixed in place:**
  1. `msiexec /x` the MSI (if it installed);
  2. copy `$b\program-files-sunshine` back to `C:\Program Files\Sunshine` and `$b\config` into it;
  3. re-register the service with the April install's own script, `scripts\install-service.bat`
     from the copied folder (preflight A2 confirms it exists). Fallback:
     `sc.exe create SunshineService binPath= "\"C:\Program Files\Sunshine\tools\sunshinesvc.exe\"" start= auto`.
     Then `Start-Service SunshineService`;
  4. the firewall as in C.
- RDP is untouched in every case. Only console-mode streaming depends on Sunshine.
