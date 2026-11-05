---
doc_type: design
hypothesis: null
status: ACCUMULATING
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: []
next_action: Sections 1-6 applied. The Thai copy (section 5) was DONE 2026-10-03 (434 files hash-verified, revoked at once, @pristine-20261003). Next: Part C (C1-C5, docs/locale-packs.md); the kRO reference table must still be sourced (no _scratch extract exists).
---

# poring-lab on TrueNAS: the dataset sink and the Thai copy

**Status: APPROVED by Batt (2026-10-02).**
- Sections 1–3 APPLIED on TrueNAS at 20:18–20:20.
- Section 4 applied by Batt (fstab backed up to `/etc/fstab.bak-20261002-poring`).
- **Section 6 PASSED at 21:06** (see the end).
- Section 5 (the Thai copy) is next in the agreed order.

**Section 4 as applied:**
- fs type `nfs4` (§4 below says `nfs` + `nfsvers=4.2`);
- no explicit `rw`;
- a comment line.

Option sets otherwise identical, functionally the same. Live:
`soft,vers=4.2,timeo=150,retrans=3,noatime,rsize/wsize=1M`, datasets and locale-packs rw, Thai ro;
three automount units with a 10 min idle timeout.

**Applied, and read back the same minute:**

| Object | Id / value |
|---|---|
| Datasets | `tank-main/poring-lab` (2T, 1M, lz4, atime off, quota alarms 80/95), `…/datasets`, `…/thai-client-data` (20G), `…/locale-packs` (10G, 128K) |
| Ownership | datasets and locale-packs `1000:1000 750`; thai-client-data `3000:1000 755` |
| NFS exports | ids **7** (datasets, rw), **8** (locale-packs, rw), **9** (thai-client-data, ro). All `192.168.1.13` only, sec=sys, no maproot/mapall. `showmount -e` from the VM lists all three |
| Snapshot task | id **14**: datasets, daily 03:15, 2 WEEK, `auto-%Y-%m-%d_%H-%M` |
| Temporary SMB drop | **not created yet**: only at the copy, to keep its life to minutes |

**Checks:**
- Before and after: Frigate StartedAt 2026-09-23T01:35:17Z, restarts 0.
- `tank-main` depth-1 datasets went 18 → 19; NFS shares 6 → 9; SMB unchanged at 7; snapshot tasks
  10 → 11.
- The midclt job flag on 25.04 is `-j` (`-job` is refused). The commands below use `-j`.

➡️ **This version supersedes the first recipe of 2026-10-02** (a new `poringlab` NAS user, Mapall,
a standing SMB drop share, `hard` mounts). Batt chose that the agent configures TrueNAS itself, so
the plan now reuses the proven patterns on this NAS and keeps write paths temporary.

**Who does what.**
- **The agent** configures TrueNAS, over `ssh root@192.168.1.6` and only through `midclt`, after the
  approval.
  - House rules (home-assistant CLAUDE.md §2.1): read-only unless approved; middleware calls only,
    never hand-edited config; every new `tank-main` dataset gets a quota (`tank-main/ix-apps`
    holds every TrueNAS app's data, Frigate's included).
- **Batt** runs one sudo block on the VM (section 4). The agent has no sudo there.

**Measured 2026-10-02 (read-only), the facts this plan rests on:**
- TrueNAS SCALE 25.04.2.6.
- `tank-main`: RAIDZ2, 70 % full, 8.91 T free.
- The NFS and SMB services are already running, so no service change is needed.
- Proven pattern: the `sec-idisc-archive` export (VM 192.168.1.13 only, no maproot/mapall, owned by
  uid 1000:1000 = the VM's `batt`, mode 750, posix ACL).
- The NAS SMB user `batt` (uid 3000) exists.
- Snapshot task 7 (pool root) is not recursive.
- Frigate (`ix-frigate-frigate-1`): StartedAt 2026-09-23T01:35:17Z, 0 restarts. Re-read before the
  change; compare against that reading, not this number.

## 1. Datasets (midclt, each read back by name)

    midclt call pool.dataset.create '{"name":"tank-main/poring-lab","type":"FILESYSTEM",
      "recordsize":"1M","compression":"LZ4","atime":"OFF","quota":2199023255552,
      "quota_warning":80,"quota_critical":95,
      "comments":"poring-lab (VM 103): dataset sink, Thai copy, locale packs; quota protects ix-apps"}'
    midclt call pool.dataset.create '{"name":"tank-main/poring-lab/datasets","type":"FILESYSTEM",
      "comments":"poring-lab recordings (scripts/dataset_ship.py)"}'
    midclt call pool.dataset.create '{"name":"tank-main/poring-lab/thai-client-data","type":"FILESYSTEM",
      "quota":21474836480,"comments":"Thai client copy + kRO reference; readonly after the copy; never committed"}'
    midclt call pool.dataset.create '{"name":"tank-main/poring-lab/locale-packs","type":"FILESYSTEM",
      "recordsize":"128K","quota":10737418240,"comments":"locale packs (scripts/locale_pack.py); never committed"}'

| Dataset | recordsize | Quota | Why |
|---|---|---|---|
| `poring-lab` | 1M | 2 TiB (warn 80 / crit 95) | the recordings are 256 MB PNG tar shards and the GRF is 3.3 GB: large and sequential. lz4 gives up early on incompressible PNG, so it costs nothing. atime off. 2 TiB is ~70 h at 489 MB/min |
| `…/datasets` | 1M (inherited) | (parent) | recordings |
| `…/thai-client-data` | 1M (inherited) | 20 G | made `readonly=on` after the copy |
| `…/locale-packs` | 128K | 10 G | small JSON/text files |

## 2. Ownership and NFS exports (to the VM only)

    midclt call -j filesystem.setperm '{"path":"/mnt/tank-main/poring-lab/datasets","mode":"750","uid":1000,"gid":1000}'
    midclt call -j filesystem.setperm '{"path":"/mnt/tank-main/poring-lab/locale-packs","mode":"750","uid":1000,"gid":1000}'
    midclt call -j filesystem.setperm '{"path":"/mnt/tank-main/poring-lab/thai-client-data","mode":"755","uid":3000,"gid":1000}'
    midclt call sharing.nfs.create '{"path":"/mnt/tank-main/poring-lab/datasets","hosts":["192.168.1.13"],"ro":false,"comment":"poring-lab dataset sink, VM 103 only"}'
    midclt call sharing.nfs.create '{"path":"/mnt/tank-main/poring-lab/locale-packs","hosts":["192.168.1.13"],"ro":false,"comment":"poring-lab locale packs, VM 103 only"}'
    midclt call sharing.nfs.create '{"path":"/mnt/tank-main/poring-lab/thai-client-data","hosts":["192.168.1.13"],"ro":true,"comment":"poring-lab Thai copy, READ-ONLY, VM 103 only"}'

- **No maproot/mapall.** NFSv4 with sec=sys passes the VM's uid 1000 straight through, the same as
  `sec-idisc-archive`, so no NAS user is needed for the VM.
- **`thai-client-data` is owned by the NAS `batt` (3000).** His SMB account writes it during the
  copy (section 5), and the VM reads it as "other" (755) over a read-only export.

## 3. Snapshots

    midclt call pool.snapshottask.create '{"dataset":"tank-main/poring-lab/datasets","recursive":false,
      "lifetime_value":2,"lifetime_unit":"WEEK","naming_schema":"auto-%Y-%m-%d_%H-%M",
      "schedule":{"minute":"15","hour":"3","dom":"*","month":"*","dow":"*"},"enabled":true}'

- Daily at 03:15, kept 2 weeks (the house convention): a 2-week undo for a mistaken `prune`.
- After the Thai copy: a one-off `thai-client-data@pristine-<date>` (section 5).

## 4. The VM (Batt runs this block; sudo)

    sudo mkdir -p /mnt/poring-lab-datasets /mnt/poring-thai-src /mnt/poring-locale-packs
    printf '%s\n' \
     '192.168.1.6:/mnt/tank-main/poring-lab/datasets         /mnt/poring-lab-datasets nfs _netdev,nofail,x-systemd.automount,x-systemd.idle-timeout=600,x-systemd.mount-timeout=30,nfsvers=4.2,soft,timeo=150,retrans=3,noatime,rw 0 0' \
     '192.168.1.6:/mnt/tank-main/poring-lab/thai-client-data /mnt/poring-thai-src     nfs _netdev,nofail,x-systemd.automount,x-systemd.idle-timeout=600,x-systemd.mount-timeout=30,nfsvers=4.2,soft,timeo=150,retrans=3,noatime,ro 0 0' \
     '192.168.1.6:/mnt/tank-main/poring-lab/locale-packs     /mnt/poring-locale-packs nfs _netdev,nofail,x-systemd.automount,x-systemd.idle-timeout=600,x-systemd.mount-timeout=30,nfsvers=4.2,soft,timeo=150,retrans=3,noatime,rw 0 0' \
     | sudo tee -a /etc/fstab
    sudo systemctl daemon-reload && sudo systemctl restart remote-fs.target

**Why `soft`, unlike the existing `hard` mounts.** On 2026-09-10 a NAS fault hung the whole guest
through a hard NFS mount. With these options:
- a NAS outage costs the lab an IO error after about a minute, not a hung VM;
- `nofail` + automount mean the boot never waits;
- `idle-timeout=600` unmounts when idle, so an outage while idle touches nothing.

**Soft mounts can lose writes silently, and both writers are covered:**
- `dataset_ship.py` re-hashes every file ON the NAS before it deletes the local copy;
- recordings are written to local disk, never to NFS.

**These mounts are never bind-mounted into a container**, with ONE exception (Batt, 2026-10-04):
- the **vision** container reads the datasets export **read-only** for training, through its own
  NFS volume (`compose.yaml` `datasets-nas`: `ro,soft`, mounted by dockerd from this VM, vision only,
  `tests/test_guards.py`);
- the host mount stays the only writer: the frame cache's shards under `.framecache/` are written by
  `scripts/build_frame_cache.py` on the host and read back (ADR-0010 note).

## 5. The Thai copy (a temporary, least-privilege write path)

The exports above are VM-only and the Thai one is read-only, so Windows can't write through them.
The copy uses Batt's EXISTING NAS account, for one named IP, for minutes:

    midclt call sharing.smb.create '{"name":"poring-thai-drop","path":"/mnt/tank-main/poring-lab/thai-client-data",
      "purpose":"MULTI_PROTOCOL_NFS","browsable":false,"hostsallow":["192.168.1.169"],"hostsdeny":["ALL"],
      "comment":"TEMPORARY: the Thai copy from the Dell; delete after the copy (poring-lab)"}'

1. **Batt authenticates** at Windows' credential prompt as `batt`, without saving the credential.
   - He **pastes** the password through the web console's clipboard (ADR-0004: pastes are never
     logged; typed keys would be).
   - The agent never sees it.
2. **The agent types the non-secret copy** in poring-lab's console:

       robocopy "C:\Users\poring-lab\Desktop\ro_thai" "\\192.168.1.6\poring-thai-drop\ro_thai" /E /Z /R:2 /W:5 /NP

   and the same for the WARP kRO extract (`C:\RO-rAthena\_scratch\…`) into `kro-reference\`.
3. **Hash check:** `Get-FileHash -Algorithm SHA256` on Windows against `sha256sum` on the NAS (a root
   read). The two lists must be equal.
4. **Revocation, immediately:**

       midclt call sharing.smb.delete <id>
       midclt call pool.dataset.update tank-main/poring-lab/thai-client-data '{"readonly":"ON"}'
       midclt call zfs.snapshot.create '{"dataset":"tank-main/poring-lab/thai-client-data","name":"pristine-<yyyymmdd>"}'

   Then, in poring-lab's console, `net use * /delete /y` to drop the session's cached connection.
   **As applied, 2026-10-03 12:27–13:03** (quant ±5 min; Frigate unchanged):
   - **What was copied:** the source folder turned out to be a FULL client install (an exe, 35
     DLLs, `savedata\`, `PatchClient\`). Only the data documented in locale-packs.md §1 went: the
     two GRFs (`data.grf` 3,303,242,041 B, `event.grf`), `System\` (18 files) and `skin\`
     (414 files), with `/XF *.exe *.dll *.asi *.m3d`. `savedata\` (personal) and `PatchClient\`
     (a program) were NOT copied.
   - **Integrity:** 434 files, 3.09 GB at ~6 MB/s (the Dell side was the limit). The Windows source
     hashes were written to the share (`_windows-ro_thai.sha256`) and compared with `sha256sum`
     on the NAS: 434 = 434, 0 mismatches.
   - **Revoked at once:** share id 19 deleted (0 sessions); `readonly=ON` (a write probe gets
     "Read-only file system"); `@pristine-20261003` (2.71 GB); `net use … /delete`; 0 saved
     credentials (`cmdkey`).
   - **Not copied: the kRO reference table.** `C:\RO-rAthena\_scratch\` does not exist (the WARP
     output was never kept). The Korean table lives only in the never-run kRO exe, so it is a
     Part C decision.
5. **The locale-pack install (C5) uses the same pattern:** a temporary **read-only** share on
   `locale-packs/th`, Dell-only, deleted right after the install.
   ➡️ **2026-10-03, as a GUEST share (Batt's approval): created and deleted, unusable.** Share
   id 20 `poring-locale-th` (ro, guestok, not browsable, hostsallow 192.168.1.169, hostsdeny
   ALL; 15:40, read back) was refused by Windows itself: insecure guest logons are blocked
   (error 1272). Deleted at 15:44 (read back: no poring SMB share; no sessions); Frigate unchanged
   before/after. See [locale-packs.md](../locale-packs.md) §6 for the open decision.

**From 2026-10-03 the share steps above are one command each way: `scripts/nas_drop.py`**
(Batt approved). `open NAME --dataset … [--subdir P] --host 192.168.1.169 [--rw [--unlock]]`
creates an AUTHENTICATED share (never guest), Dell-only, not browsable, tagged `TEMPORARY
poring-lab nas_drop`, and reads it back; `--unlock` snapshots `pre-drop-<stamp>` BEFORE lifting
readonly. `close NAME [--lock]` deletes only a tagged share, reads back that it is gone, lists
sessions still on it and, with `--lock`, sets readonly + `@pristine-<stamp>`. Both take a Frigate
reading before and after. `status` lists open drops.

## 5b. `kro-reference` (2026-10-03): the two client exes, bytes only

    midclt call pool.dataset.create '{"name":"tank-main/poring-lab/kro-reference","type":"FILESYSTEM",
      "quota":1073741824,"comments":"poring-lab: the lab kRO exe + the Thai client exe, BYTES ONLY for
      offline msgtable parsing (never executed); readonly; no shares/exports; never committed"}'

- Filled from the human-only transfer area on Batt's instruction (ADR-0004 "Exceptions log"):
  `docker exec … cat /transfer/<exe> | ssh root@nas 'umask 0377; cat > …'`, mode 0444, root-owned.
- `lab-2021-11-03_Ragexe_1635926200.exe` sha256 `3f11ce85…1c3baa35`;
  `thai-ro_thai-Ragexe.exe` sha256 `6f1b3451…7f4ab8f2`; `SHA256SUMS` beside them (both OK).
- Then `readonly=ON` (a write probe: "Read-only file system") and `@pristine-20261003`. No SMB
  share, no NFS export: the VM reads it only through root ssh, into `/dev/shm`.

## 6. The agent's checks, after section 4

**Mounts:**
- `mount | grep poring` shows the three mounts, each `soft`, with automount;
- `ls` of each.

**Probes:**
- a write to `/mnt/poring-thai-src` must fail (`Read-only file system`);
- write, read and delete a test file in `/mnt/poring-lab-datasets` and `/mnt/poring-locale-packs`.

**The ship round-trip** (ADR-0010, "Implementation"), outside SET hours (09:30–17:00 Bangkok on
weekdays; `ship` refuses then, unless `--force-market`), with quant-postgres 5 min before and after:
1. A 30-second recording on local disk:

       uv run python scripts/record_session.py --backend rdp --label ship-test --seconds 30

   It goes to `/home/batt/poring-lab-rec/<session>/`; the caps are 120 GB free (140 GB until Batt's 2026-11-05 decision) and 20 GB unshipped.
2. `uv run python scripts/dataset_ship.py status` shows it `local  unshipped` and `nas …: mounted`.
3. Ship it:

       uv run python scripts/dataset_ship.py ship

   This writes `checksums.sha256`, rsyncs at `--bwlimit=40000` under the quant IO guard, re-hashes
   on the NAS, writes `storage` into the NAS manifest, appends to `INDEX.jsonl`, and only then
   deletes the local copy. It refuses if `/mnt/poring-lab-datasets` is not a mount point.
4. `status` again: the session shows `nas  verified <time>`, and nothing local remains.
   `INDEX.jsonl` has one `shipped` line.
5. `uv run python scripts/dataset_ship.py prune` is a dry run: nothing is that old yet.

Then:
- **pass → ADR-0010 ACCEPTED**;
- pin the test session only if it is worth keeping: `dataset_ship.py pin <id> --reason …`.

**NAS side:**
- every object read back by id or name;
- Frigate's StartedAt and RestartCount unchanged;
- `zfs list -r tank-main -d 1` shows only `poring-lab` added.

**The Thai copy is read only from `/mnt/poring-thai-src`.** Small extracted files go to `/dev/shm`;
the 3.3 GB GRF is never copied to the VM.

## Rollback

**NAS:**

    midclt call sharing.smb.delete <id>        # if still present
    midclt call sharing.nfs.delete <id>        # x3
    midclt call pool.snapshottask.delete <id>
    midclt call pool.dataset.delete tank-main/poring-lab '{"recursive":true}'

**VM:** delete the three fstab lines, then
`sudo systemctl daemon-reload && sudo systemctl restart remote-fs.target`.

**Windows:** `net use * /delete /y` in poring-lab's session (no credential was saved).

## Section 6 results (2026-10-02 21:01–21:07)

| Check | Result |
|---|---|
| Automounts | 3 units active; `findmnt -t nfs4` shows soft, v4.2, timeo 150, retrans 3, noatime; datasets/locale-packs rw, Thai ro |
| Read-only refusal | `touch /mnt/poring-thai-src/probe` → `Read-only file system` |
| Probes | write/read/delete OK in datasets and locale-packs, as uid 1000:1000; 0 probe files left on the NAS |
| Round-trip | `20261002T210604-rdp-ship-test`: 204 frames, 140.7 MB → `ship` (2 files, NAS-verified 21:06:51) → local copy gone (only the empty `.ship.lock` remains) → `status` shows `nas verified`; NAS-side `sha256sum -c` OK for both files; manifest `storage` + `INDEX.jsonl` `shipped` line; `prune` dry run deletes nothing |
| Quant | quant-postgres io_full 3.02 → 3.66 % (record), 3.89 → 2.63 % (ship); one 10 s bin at 17.4 % during the 30 s local PNG write |

**Verdict: PASS. ADR-0010 is ACCEPTED.**

