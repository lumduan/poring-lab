# Moving a Sunshine-only Windows PC to RDP

*(Written 2026-11-19 for the live copy, Batt's second Windows PC at 192.168.110.96, on Batt's
request: "keep this, I will have to explain it to other people simply".)*

## In one paragraph (to explain it to someone else)

The bot needs to see the game and press keys on a Windows PC. There are two ways for it to reach that PC:
- **Sunshine**: a streaming app on the PC that sends the screen as video;
- **RDP**: Windows' own Remote Desktop.

Before the bot types anything, a safety check (the "UI gate") compares the screen with template
pictures, to be sure no game window or NPC dialog is left open. Those pictures exist only as they look
through RDP. Video compression softens them, and nobody has yet cut the Sunshine set. So on a
Sunshine-only PC the safety check refuses every Run.

The quick fix is to give that PC RDP as well:
- a separate, ordinary Windows account just for the bot (`poring-lab`, not an administrator);
- Remote Desktop switched on, open only to the bot server;
- the bot server signs in as that account.

The bot then works through the same proven path as the lab.

| | Sunshine (before) | RDP (now) |
|---|---|---|
| what the console shows | the person's own Windows desktop | the bot account's own desktop (a fresh Windows profile) |
| the safety check's pictures | not cut yet: every Run refuses | proven (the lab's set) |
| the person's own session | is the one being streamed | is **disconnected** (not signed out: programs stay open) while the bot account holds the PC |
| who may connect | the paired lab client only | the bot server only (firewall), with the bot account's password |

Windows client editions (Home, Pro) allow **one** session at a time. When the bot account signs in,
the person's session is disconnected. When the person signs in at the PC again, the bot's RDP
session is disconnected. Never connect with a second RDP or streaming client while the lab runs
(ADR-0001).

## Who does what, in order

```
  bot host                    Windows PC (admin PowerShell)        bot host
  1. make the password  --->  2. create the account, RDP on,  ---> 3. pin the certificate
                                 firewall to the bot host          4. ONE credential check
                                                                   5. recreate the desktop
                                                                   6. to-rdp
                                                                   7. answer the sign-in screen
```

1. **The password (bot host).** In the copy's folder:

        uv run python scripts/rotate_secrets.py rotate WIN_LAB_PASSWORD

   Copy the same value into `RDP_PASSWORD`. Set `WIN_LAB_USER` and `RDP_USER` to `poring-lab`, in
   a text editor (`rotate_secrets.py set` refuses names that look secret). The password is never
   printed in a report or a chat.

2. **The account and Remote Desktop (Windows, an administrator's PowerShell).**
   - A person opens PowerShell **as administrator** and answers UAC; the agent never does.
   - The password goes only into the hidden `Read-Host -AsSecureString` prompt, never onto a
     command line: a command line lands in PSReadLine's history.
   - The groups are named by their fixed SIDs, so a Thai or any other display language works.

        (Get-CimInstance Win32_OperatingSystem).Caption      # must say Pro / Enterprise / Education
        $pw = Read-Host -AsSecureString 'poring-lab password'
        New-LocalUser -Name 'poring-lab' -Password $pw -PasswordNeverExpires -UserMayNotChangePassword -AccountNeverExpires | Out-Null
        Add-LocalGroupMember -SID 'S-1-5-32-545' -Member 'poring-lab'    # Users
        Add-LocalGroupMember -SID 'S-1-5-32-555' -Member 'poring-lab'    # Remote Desktop Users
        Remove-Variable pw
        Set-ItemProperty 'HKLM:\System\CurrentControlSet\Control\Terminal Server' -Name fDenyTSConnections -Value 0
        Get-NetFirewallRule -Group '@FirewallAPI.dll,-28752' | Set-NetFirewallRule -RemoteAddress <BOT_HOST_IP> -Enabled True

   Check: `Get-LocalGroupMember -SID S-1-5-32-555` lists the account, and
   `Get-LocalGroupMember -SID S-1-5-32-544` (Administrators) does NOT. Windows **Home cannot host
   RDP**: on Home this whole page does not apply.

3. **Pin the PC's certificate (bot host).** This is a pre-login handshake only:

        python3 scripts/rdp_cert_fingerprint.py <WIN_PC_IP>
        uv run python scripts/rotate_secrets.py set RDP_CERT_SHA256=<the printed hex>

4. **One credential check, before anything connects (bot host).**
   - FreeRDP's `/auth-only` does the network login (NLA) and exits. It opens no session, so
     nobody's desktop is touched.
   - Feed it the same arguments `rdp-loop.sh` uses, on stdin (`/args-from:stdin`), never on a
     command line.
   - Read the result:
     - `Authentication only, exit status 1`: accepted;
     - `ERRCONNECT_LOGON_FAILURE`: no such account or a wrong password.
   - Try it **once**, then find out why it failed. Repeated failures lock the account, and the RDP
     loop must never retry fast on an auth failure (CLAUDE.md rule 2).
   - The `krb5_parse_name ... default realm` lines are normal: a local account falls back from
     Kerberos to NTLM.

5. **Recreate the desktop (bot host).** The desktop container reads `RDP_*` only when it is
   created:

        python3 scripts/guarded_build.py --sustain 30 --spike 25 recreate:desktop@60

6. **Hand the PC to RDP (bot host):**

        python3 scripts/capture_backend.py to-rdp

   Use plain `to-rdp`. `to-rdp --sunshine-only` refuses once RDP is configured: it is for hosts
   with no RDP at all. The handover ends the Sunshine stream, then waits 15 s for Sunshine to undo
   its display settings. It writes the lock `rdp`, and ends with exactly one RDP client.

7. **The Windows sign-in screen, when someone is signed in at the PC.**
   - The screen asks: "Another user is signed in. If you continue, they'll be disconnected. Do you
     want to sign in anyway?". Answer **Yes**.
   - Move the pointer onto the button first, then click. A click with no hover before it was
     ignored (2026-11-19).
   - Windows then shows "Please wait for <the signed-in user> to respond". With no answer it
     allows the sign-in on its own after about 30 s.
   - The first sign-in of a new account takes another minute or two, while Windows builds the
     profile. It ends on the bot account's desktop, with Edge's first-run screen in front.

## What happened on 2026-11-19 (the live copy, 22:06-22:31 ICT)

| ICT | what | why it matters |
|---|---|---|
| 22:06 | a live Run refused: `ui gate: the s2 template set is not proven` | the gap above; Batt chose RDP first (option A), the Sunshine set later (option B) |
| 22:1x | `.env` password made and copied (step 1) | |
| 22:18 | port 3389 answered; the certificate pinned (step 3) | RDP was already on |
| 22:19 | the credential check: `ERRCONNECT_LOGON_FAILURE` | the account did not exist: the commands had come back pasted into the chat, not run. The one-shot check caught it before any session or lockout |
| 22:20-22:24 | Batt left an admin PowerShell open and delegated this one task; the agent typed the lines through the live console. Each line waited until the PowerShell title bar was in front; the password went into the hidden prompt, re-checked every 4 characters | Windows 11 Pro; account created; groups checked; RDP rules limited to 192.168.1.228 |
| 22:23 | the credential check: accepted | |
| 22:27 | `recreate:desktop` OK | |
| 22:28-22:29 | `to-rdp`: exactly one RDP client, lock `rdp/steady` | Sunshine's revert check did not run: it reads Sunshine's log through the lab PC's own shell, which this PC does not have |
| 22:29-22:31 | sign-in screen: Yes (with a hover), the 30 s wait, the first sign-in | the bot account's desktop is up; Batt takes over from here |

## Still open (Batt's, on that PC)

- **The game client lives under `C:\Program Files (x86)`.**
  - A standard account may only read and run files there (`Users: ReadAndExecute`).
  - Nothing has been checked yet: whether the client must write into its folder, or asks for
    administrator rights at launch. Nothing was changed there, at Batt's request ("you just log
    in; I handle the rest").
  - If it must write there, the lab's pattern is Modify on that one folder for `poring-lab`
    (`icacls "<folder>" /grant "poring-lab:(OI)(CI)M"`), never an administrator account.
- **The bot account's own Windows settings:**
  - sleep, the screen lock and the screensaver off (a locked session shows the lock screen to the
    bot);
  - display scale 100 %;
  - a desktop shortcut to the game.
- **The Settings page of the live console:** this PC's environment entry (a person's act).

## Going back to Sunshine (not tried on this PC)

- `to-console --yes-tscon` needs the lab-only tscon task on Windows (ADR-0019), which this PC does
  not have.
- The way back for a PC without it:
  1. empty `RDP_USER` / `RDP_PASSWORD`;
  2. `recreate:desktop`;
  3. `to-console --sunshine-only`.
- The bot account's session is then disconnected, and the PC's screen shows Windows' sign-in.
- The lasting fix for Sunshine-only learners is the S2 template set
  ([s2-gate-templates.md](../operations/s2-gate-templates.md), teaching-prerun row 25).

Related: [new-lab-host.md](new-lab-host.md) sections 7.2-7.3 (the same account and RDP steps for
a new lab host), [windows-lab-host.md](windows-lab-host.md) (the lab PC), ADR-0001 (one session),
ADR-0009 (the capture-backend lock), ADR-0019 (Windows stays clean).
