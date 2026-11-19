---
doc_type: runbook
hypothesis: null
status: ACTIVE
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [../windows-setup.md, new-lab-host.md, ../operations/sunshine-msi-replace.md, ../operations/console-display.md, ../console-capture-plan.md, ../adr/0009-console-session-capture.md, ../adr/0014-s2-primary-bot-path.md, ../adr/0019-windows-stays-clean.md, ../operations/s2-gate-templates.md]
next_action: "Students follow it BEFORE ./setup.sh. Every step that reads differently on a real PC is fixed HERE. The 'What works' section changes when the S2 UI-gate templates are proven (s2-gate-templates.md)."
title: "Sunshine on the Windows game PC, for ./setup.sh"
date: 2026-11-17
owner: Batt
---

# Sunshine on the Windows game PC

Do this on the Windows PC **before** you run `./setup.sh` on the bot server. The setup wizard asks
for the PC's address, tests Sunshine, and pairs with it, so Sunshine must already be installed and
running.

**What you get.** The PC streams its screen to the bot server with Sunshine. The server's own
client (the `gamestream` service) shows that stream in the web console, and your mouse and
keyboard travel back the same way. There is no Remote Desktop (RDP) in this setup.

**You need:**
- the Windows PC that runs the game, on the same LAN as the bot server;
- an administrator account on the PC for the install and the firewall step (the game itself runs
  as a normal user);
- the bot server's LAN address (step 4 shows how to find it).

Two addresses come up everywhere below: `<BOT_SERVER_IP>` (the Linux server) and `<PC_IP>` (this
Windows PC).

## 1. Install Sunshine (the signed installer)

1. Download **`Sunshine-Windows-AMD64-installer.msi`** from LizardByte's Sunshine releases on
   GitHub (`github.com/LizardByte/Sunshine`, Releases). The lab runs **v2026.914.233613**
   ([docs/operations/sunshine-msi-replace.md](../operations/sunshine-msi-replace.md)).
   - Use the **MSI**: LizardByte signs the MSI installer. (The program files inside it carry no
     signature of their own; the lab checked that they are exactly the MSI's contents.)
   - Not the portable zip and not another fork: the lab's decisions are for upstream Sunshine
     (ADR-0009; a fork that syncs the clipboard was rejected).
2. Check the file before you run it, in PowerShell:

   ```powershell
   Get-AuthenticodeSignature "$HOME\Downloads\Sunshine-Windows-AMD64-installer.msi" | Format-List Status, SignerCertificate
   Get-FileHash "$HOME\Downloads\Sunshine-Windows-AMD64-installer.msi" -Algorithm SHA256
   ```

   `Status` must be `Valid`. For v2026.914.233613 the SHA-256 is
   `1D7FED8BEECD5889DC7FF14CF9F42D6D38F37C3066C13C6C2A5F4E91847E0CCF` (the lab compared it with
   GitHub's own digest for that release). For a newer release, compare with the digest GitHub
   shows next to the file.
3. Double-click the MSI and keep the defaults. It installs Sunshine **as a Windows service**
   (`SunshineService`, started automatically) and adds Windows firewall rules for it (step 4
   narrows them).
4. Check, in PowerShell: `Get-Service SunshineService` shows `Running`.

## 2. First start: your own Sunshine login

1. On the PC, open **https://localhost:47990** in a browser.
2. The browser warns that the site is not secure: Sunshine uses a self-signed certificate. That is
   expected; continue to the page.
3. The first page asks you to create a **username and password for Sunshine's web page**. Choose
   them and keep them yourself.
   - This login is YOURS. The setup wizard never asks for it, and it is never stored on the bot
     server. Type it only into Sunshine's page on the PC.

## 3. Keep Sunshine's web page on the PC only

By default Sunshine's page is open to the whole LAN. The lab keeps it **PC-only**
(`origin_web_ui_allowed = pc`, ADR-0009).

1. In Sunshine's page: **Configuration**, the **Network** settings, **Origin Web UI Allowed**:
   choose **Only localhost may access Web UI**. Save the change (if the page asks to apply or
   restart, do so).
2. Or, as an administrator, add this line to `C:\Program Files\Sunshine\config\sunshine.conf`
   and restart the service (`Restart-Service SunshineService`; it can take ~30 s to stop):

   ```text
   origin_web_ui_allowed = pc
   ```

3. Check: from another computer, `https://<PC_IP>:47990` must NOT show Sunshine's page. On the
   PC itself, `https://localhost:47990` still works.

## 4. The firewall: admit only the bot server

The installer's rules let any address reach Sunshine. Narrow them to the bot server.

1. **Find the bot server's address.** On the bot server: `ip -4 route get 1.1.1.1` and read the
   address after `src` (the setup wizard's screen 1 shows the same address). That is
   `<BOT_SERVER_IP>`.
2. On the PC, in an **administrator** PowerShell (exactly the installed program's path; the lab's
   runbook uses the same command):

   ```powershell
   $exe = 'C:\Program Files\Sunshine\sunshine.exe'
   Get-NetFirewallApplicationFilter -Program $exe | Get-NetFirewallRule | Set-NetFirewallRule -RemoteAddress <BOT_SERVER_IP>
   Get-NetFirewallApplicationFilter -Program $exe | Get-NetFirewallRule |
     ForEach-Object { '{0} {1} {2}' -f $_.DisplayName, $_.Enabled, (($_ | Get-NetFirewallAddressFilter).RemoteAddress -join ',') }
   ```

3. Check the read-back: every listed rule is `True` (enabled) and names only `<BOT_SERVER_IP>`.
   These are program rules, so they cover Sunshine's TCP **and** UDP ports (the table in step 9).
4. If the bot server's address ever changes, run step 2 again with the new address.

## 5. A display Sunshine can capture

Sunshine streams a display, not a window. It needs a display that is on:
- **a monitor** that stays switched on and connected; or
- **a virtual display driver** (no monitor needed). The lab uses one ("VDD by MTT") at
  **1440 × 900**, the lab's session size, as the only display
  ([docs/operations/console-display.md](../operations/console-display.md); Sunshine's
  `dd_configuration_option = ensure_only_display` keeps it that way during a stream).

The stream asks for 1440 × 900 (`SESSION_SIZE`). A desktop of that size keeps the game window and
the console 1:1. A display that is off, asleep or unplugged gives a **black** stream: the wizard's
stream test reports it.

## 6. A fixed address for the PC

1. Read the PC's address: in PowerShell or a command prompt, `ipconfig`. The **IPv4 Address** line
   of the network you use (Ethernet or Wi-Fi) is `<PC_IP>`. `ipconfig /all` also shows its
   **Physical Address** (the MAC address).
2. Make it fixed: in your router's settings, add a **DHCP reservation** for that MAC address, so
   the PC always gets the same IPv4 address. (Every router names this differently; look for
   "DHCP reservation" or "static lease".)
3. **Any address works** (since 2026-11-17, Batt: "don't lock an IP"; ADR-0026). The wizard
   writes your PC's address as `WIN_HOST`; the safety interlock's environment set takes it at its
   first start, and you can change an environment's Windows PC later on the console's Settings
   page ("Set Windows PC"). The packet sniffer follows `WIN_HOST` too, and its packets only label
   a session "verified", never stop the bot. (Before 2026-11-17 only 192.168.1.169 worked.)

## 7. Never asleep, never locked, always logged in

Sunshine streams what is on the PC's own screen. If the PC sleeps, locks or shows the sign-in
screen, that is what the stream shows.
- **Sleep and screen off: Never.** Settings, System, Power: screen and sleep both "Never". Or, in
  PowerShell: `powercfg /change standby-timeout-ac 0` and `powercfg /change monitor-timeout-ac 0`.
- **No screen saver.** Settings, Personalization, Lock screen, Screen saver: (None).
- **No sign-in after being away.** Settings, Accounts, Sign-in options: when Windows should
  require you to sign in again after being away: Never.
- **Stay logged in at the PC.** Log in at the PC itself, and leave that session there. Do not
  connect to the PC with Remote Desktop: it takes the PC's one session away from the screen
  Sunshine streams (Windows allows one interactive session, ADR-0001).

## 8. Pairing, during the wizard

You pair once, when the wizard reaches **screen 6, "Pair with Sunshine"**. The wizard shows a
4-digit **PIN**: a single-use code, not a password.

1. In the wizard, choose **Start pairing now**. The bot server now asks Sunshine to pair and waits
   (about 3 minutes). Sunshine accepts a PIN only while such a request waits, so type it after
   this, not before.
2. On the PC, open **https://localhost:47990** and log in with your Sunshine login (step 2).
3. Click **PIN** in the page's top bar.
4. Type the wizard's 4 digits into the PIN field, and a **Device Name** of your choice (for
   example `poring-lab`).
5. Click **Send**. "Success! Please check Moonlight to continue" means done; the wizard sees it by
   itself and goes on. ("Moonlight" is the stream protocol's client family; here it is the bot
   server's own client.)
6. "Pairing Failed: Check if the PIN is typed correctly": start the pairing again in the wizard (it
   shows a new PIN) and type the new one.

**Pair only the bot server.** Exactly one client may be paired with this Sunshine: the lab's.
Another paired device (a phone, a laptop with Moonlight) would be a second input path around the
bot server's safety checks (ADR-0009). To remove a pairing, use that device's own delete button in
Sunshine's list of paired clients, never an "unpair all".

## 9. Check and fix

**The ports** (Sunshine's defaults, from its own Network settings page; the program rules of step
4 cover all of them):

| Protocol | Port | What | Reached from |
|---|---|---|---|
| TCP | 47984 | HTTPS: pairing, starting a stream | the bot server |
| TCP | 47989 | HTTP | the bot server |
| TCP | 48010 | RTSP: the stream's setup | the bot server |
| UDP | 47998 | video | the bot server |
| UDP | 47999 | control (your mouse and keyboard) | the bot server |
| UDP | 48000 | audio (the lab keeps audio on the PC) | the bot server |
| TCP | 47990 | Sunshine's web page | the PC itself only (step 3) |

The wizard tests TCP 47984, 47989 and 48010 on screen 3 (the same test as
`scripts/capture_backend.py`). The UDP ports carry the stream itself: the stream test on screen 7
proves them.

| What the wizard says | Check |
|---|---|
| Sunshine does not answer (screen 3) | `Get-Service SunshineService` is `Running`; the firewall read-back of step 4 names THIS server's address; the PC is awake; `<PC_IP>` is still the PC's address (`ipconfig`); `ping <PC_IP>` from the bot server answers |
| Pairing did not complete (screen 6) | the PIN typed on the PC within ~3 minutes, after "Start pairing now"; exactly the 4 digits shown; the same failure twice: restart Sunshine (`Restart-Service SunshineService`, administrator) or reboot the PC, then pair again |
| The stream did not start, or no frame (screen 7) | UDP 47998-48000 not blocked (step 4's rules are program rules: re-run its read-back); somebody logged in at the PC (step 7) |
| The frame is black (screen 7) | the display is off, asleep or not the one Sunshine captures (step 5); the screen saver or sleep (step 7) |
| The encoder | Sunshine's page on the PC, **Troubleshooting**, shows its log. If no hardware encoder starts, set the `encoder` setting to `software` (Configuration) and try again |

From the bot server, `./setup.sh --check` re-tests Sunshine's ports, the services and the pairing
any time, without changing anything.

## 10. Nothing else goes on the PC ("Windows stays clean")

The PC has one job: run the game and stream it
([ADR-0019](../adr/0019-windows-stays-clean.md)). Everything else lives on the bot server.
- On the PC: the game client (a separate copy, [docs/windows-setup.md](../windows-setup.md)
  sections 1 and 2), Sunshine, and a display. Nothing more.
- **Never install for poring-lab:** a program, script or scheduled task that runs; keys or tokens;
  a reporting channel to the server; another remote-desktop or streaming tool; antivirus
  exclusions.

## 11. What works on this path, and what does not (the known limit)

The lab itself runs on RDP. This Sunshine path ("S2", the console stream) is the bot's designed
primary path ([ADR-0014](../adr/0014-s2-primary-bot-path.md)), and it is not finished:

| | On the Sunshine-only path today |
|---|---|
| **Seeing the PC** in the console | **works** (the S2 client's frames, through the frame bus) |
| **Playing as a person** through the console | **works** (your mouse and keyboard go through the input mux to the S2 client, then to Sunshine) |
| Paste and file transfer | ➡️ **paste works since 2026-11-19**: the console types it into Windows through Sunshine, in HUMAN or ASSIST, up to 4096 bytes (ADR-0004 amendment e). File transfer is still **not available** (it needs the RDP session) |
| **The bot's typed lines** (chat, GM commands) | **refused, every one.** The UI gate types only after reading the client from pixels with templates PROVEN on the same display path. The S2 set (`data/ui_anchors/s2`) is not cut or proven anywhere yet ([s2-gate-templates.md](../operations/s2-gate-templates.md)), so it fails closed: nothing is typed. The typing-only foreground gate also refuses every bot key until its stream template is cut on this path |
| **The bot's programs** (the dungeon runner, hunt, farm, agent_play) | **do not run.** They refuse a console lock (their cursor references exist for RDP only) or stop at the UI gate at their start |
| A single bot click (e.g. `ro_agent.py click`) | passes the mux only in ASSIST or BOT (a person switches the mode) AND while the safety interlock is green (your servers confirmed on the Settings page, and the environment's Windows host matching this install's `WIN_HOST`, ADR-0023 decision 4), or in ASSIST during a short operator window. Everything else is refused |

**The workaround today: add RDP to the same PC** (Windows Pro or better): a standard bot account, Remote Desktop open to the bot server only, then the handover to RDP. The bot then uses the lab's proven RDP templates. Step by step, in plain words: [sunshine-to-rdp.md](sunshine-to-rdp.md) (done for the live copy 2026-11-19).

On a new host, every UI template (on either path) is cut from YOUR client: [new-lab-host.md](new-lab-host.md)
section 8.
