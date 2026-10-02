---
doc_type: design
hypothesis: null
status: ACCUMULATING
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: []
next_action: APPROVED by Batt and sections 1-3 APPLIED on TrueNAS 2026-10-02 20:18-20:20 (read back, Frigate unchanged). Waiting for Batt's section 4 VM sudo block; then section 6 (checks + 30 s ship round-trip -> ADR-0010 ACCEPTED), then the section 5 Thai copy with Secret typing on.
---

# poring-lab on TrueNAS: the dataset sink and the Thai copy

**Status: APPROVED by Batt (2026-10-02). Sections 1–3 APPLIED on TrueNAS at 20:18–20:20.
Section 4 (the VM) is waiting for Batt; section 5 (the Thai copy) waits for section 6.**

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

**These mounts are never bind-mounted into a container.**

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
5. **The locale-pack install (C5) uses the same pattern:** a temporary **read-only** share on
   `locale-packs/th`, Dell-only, deleted right after the install.

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

   It goes to `/home/batt/poring-lab-rec/<session>/`; the caps are 140 GB free and 20 GB unshipped.
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
