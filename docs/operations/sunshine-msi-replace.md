---
doc_type: design
hypothesis: null
status: ACCUMULATING
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: []
next_action: APPLIED 2026-10-02 21:41-22:15 (A-D, plus Batt's additions b and c). Remaining -- (c) the portable copy's removal in Batt's console, then S2 step 0.
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
    $exe = 'C:\Program Files\Sunshine\sunshine.exe'
    Get-NetFirewallApplicationFilter -Program $exe | Get-NetFirewallRule | Set-NetFirewallRule -RemoteAddress 192.168.1.13
    Start-Service SunshineService
    Get-NetFirewallApplicationFilter -Program $exe | Get-NetFirewallRule |
      % { '{0} {1} {2}' -f $_.DisplayName, $_.Enabled, (($_ | Get-NetFirewallAddressFilter).RemoteAddress -join ',') }

**Notes on C:**
- **The install is default** (`/qb`: a progress bar, no choices), logged to the backup folder.
- **The restore runs with the service stopped,** so the MSI's fresh state can't overwrite it. The
  restored hashes must equal A3's.
- **The firewall:** every rule bound to the new `sunshine.exe` is set to `RemoteAddress
  192.168.1.13` (CLAUDE.md rule 2), then read back.
  ➡️ **FIXED 2026-10-02 after the run:** the original step matched `-like '*\Sunshine\sunshine.exe'`.
  That also matched a portable copy's `…\portable\sunshine\sunshine.exe` and raised two harmless
  errors (see "As applied"). It now names the exact installed path.

Batt closes the elevated console.

## D. Verify (the agent; read-only on Windows plus the lab side)

| # | Check | Pass |
|---|---|---|
| 1 | Uninstall registry | one `Sunshine` entry, an MSI `{GUID}` key, DisplayVersion 2026.914.233613; the April entry gone |
| 2 | ~~`Get-AuthenticodeSignature 'C:\Program Files\Sunshine\sunshine.exe'` → Valid~~ ➡️ **corrected**: LizardByte signs only the MSI. The exe has no Authenticode signature upstream; the lite.zip copy carries a bogus security directory pointing past the end of the file. The check is now that **the installed exe and service binary are byte-identical to the payload of the signed, digest-verified MSI** | sha256 equal (see "As applied") |
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

## As applied (2026-10-02 21:41–22:15)

| Step | Result |
|---|---|
| A | MSI sha256 == GitHub digest, signature Valid (David Lane). `cakey.pem` not readable by poring-lab. Service Running/Auto/LocalSystem. `install-service.bat` present. **Unexpected:** two DISABLED any-address firewall rules for a portable Sunshine at `C:\Users\badso\Downloads\sunshine-windows-amd64-portable\`; `sunshine_state.json` (+ .bak) readable by poring-lab. Reported; Batt decided (b) + (c). (➡️ Correction at (c): the portable FOLDER did not exist. A had inferred it from the rules' program path) |
| B | service stopped; admin-only backup (142 files, 48.8 MB); config hashes == A; firewall exported; `uninstall.exe /S` removed service, exe and uninstall key (config\ kept) |
| C | MSI hash True; `msiexec` exit 0; config restored, hash-identical to B; service Running. The old wildcard firewall step raised 2 errors ("Defer to user" edge traversal) on the two disabled portable rules, which were left unchanged. The installed exe's two rules are enabled, `192.168.1.13` only. Stopped and asked; Batt chose to proceed (no rollback) |
| (b) | `sunshine_state.json` ACL: SYSTEM + Administrators only, not inherited. The `.bak-20261002` was deleted (a copy is in the admin-only backup). Sunshine restarted fine |
| D1 | uninstall key `{F4B3C08C-F867-4367-9465-6DAB091E5FB6}`, 2026.914.233613, LizardByte |
| D2 | exe and service binary are **NotSigned upstream**. Installed `sunshine.exe` sha256 `8e2c4627…7d571` == the MSI payload's; `sunshinesvc.exe` `823c841a…3e99e` == the MSI payload's (extracted on the VM from the digest-verified MSI with libmspack) |
| D3 | log "Sunshine version: 2026.914.233613 commit 63d35f70…"; `output_name` = the VDD; `ensure_only_display`; DISPLAY1 + DISPLAY4. ⚠️ **The pending Samsung revert was DROPPED.** The retries continued after C (21:54) but stopped at the (b) restart (21:59), and `display_device.state` disappeared. The Samsung will NOT be restored automatically |
| D4 | exactly one paired client, `poring-lab-gamestream` (read in the admin console, names only). The lab-side `moonlight list` returns Desktop / Steam Big Picture (still paired; the server cert was restored) |
| D5 | firewall: the two `Sunshine` rules for the installed exe, enabled, `192.168.1.13` only |
| D6 | `cakey.pem` and `sunshine_state.json` not readable by poring-lab |
| D7 | service Running, Auto |
| D8 | other poring-lab-readable config files (apps.json, sunshine.conf + 3 baks, logs .1–.3): 0 secret-like matches. The state file holds `username/salt/password` at top level: hence (b) |
| (c) | Preview: the only running Sunshine is `C:\Program Files\Sunshine\Sunshine.exe`; exactly 2 rules matched the EXACT program path `C:\users\badso\downloads\sunshine-windows-amd64-portable\sunshine\sunshine.exe`, both disabled. Guarded removal: "removed 2 rules"; read-back 0 rules left. **The folder never existed** ("folder exists before: False"; the `Remove-Item` "cannot find path" error is that). Only stale rules had pointed at it |

## Samsung display recovery (the pending revert was dropped, 2026-10-02)

**What happened.**
- A console stream applies `ensure_only_display`: the VDD only, the Samsung disabled.
- When the stream ended after the session had already left the console, Sunshine could not revert.
- Its pending-revert file (`config\display_device.state`) survived the reinstall, then vanished at
  the first restart of the new version (21:59).
- So nothing will re-enable the Samsung by itself.
- Batt left it off on purpose for now.

**Option 1: by hand at the Dell (Batt's choice, when convenient).**
- Press **Win+P** at the console (at the login screen or in a session), then choose **PC screen only**
  or **Extend**.
- Or use Settings → System → Display → enable the Samsung.
- This needs someone physically at the Dell. RDP mode doesn't touch the console topology.

**Option 2: one console session with Sunshine's display handling off.**
1. In an elevated console, back up `sunshine.conf`, then set `dd_configuration_option = disabled`
   and run `Restart-Service SunshineService`.
2. During one console stream (e.g. S2 step 0), open Settings → Display and enable the Samsung (or
   Win+P). With handling off, Sunshine neither enforces VDD-only nor reverts at the end, so the
   change stays.
3. Restore `ensure_only_display` from the backup and restart the service.

Cost: during that one session the stream captures whatever topology Windows has, not a fixed
1440×900 VDD.

**Prevention** (already in place): `capture_backend.py to-rdp` now ends the stream through Sunshine
(`quit` → `/cancel`) while the session is still on the console, waits, and checks the revert.

