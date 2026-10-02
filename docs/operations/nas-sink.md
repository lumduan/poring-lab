---
doc_type: design
hypothesis: null
status: ACCUMULATING
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: []
next_action: Batt applies sections 1-4 (TrueNAS UI, the VM's fstab, the Windows copy); the agent then runs section 5's checks and the first ship round-trip.
---

# poring-lab on TrueNAS: the dataset sink and the Thai drop (operator recipe)

**Who does what.**
- **Batt:** sections 1–4. The agent has no TrueNAS admin access and no root on the VM (2026-10-02).
- **The agent:** section 5.

This mirrors `quant-orderbook-engine/docs/operations/nas-cold-tier.md`, the guide every existing
export on this NAS came from.

- **NAS:** `192.168.1.6`, pool `tank-main`. **VM:** `192.168.1.13`. **Windows PC (Dell):** `192.168.1.169`.
- **Change nothing else on the NAS.** If the SMB service is off, turning it on is a NAS-wide service
  change: Batt's call. Without SMB, use the fallback in section 4.

## 1. TrueNAS: one user, four datasets

### 1.1 The user

**Credentials → Local Users → Add**:
- Username `poringlab`, full name "poring-lab (lab shares)".
- Password: **Batt's choice; never given to the agent**.
- Create a primary group `poringlab`.
- Shell `nologin`, no home directory.
- **Samba Authentication: on.**

This one user owns the lab's datasets and is the only SMB login for them.

### 1.2 The datasets

**Datasets → Add Dataset**. Every value not listed here stays at its default.

| Dataset | Share type | Compression | Atime | Record size | Quota |
|---|---|---|---|---|---|
| `tank-main/poring-lab` | Generic | LZ4 | Off | **1M** | **2 TiB** |
| `tank-main/poring-lab/datasets` | Generic | inherit | inherit | inherit | – |
| `tank-main/poring-lab/thai-client-data` | Generic | inherit | inherit | inherit | – |
| `tank-main/poring-lab/locale-packs` | Generic | inherit | inherit | inherit | – |

- **Why these values:**
  - The recordings are 256 MB tar shards of PNG, and the Thai GRF is one 3.3 GB file: large
    sequential files, hence a 1M record size.
  - LZ4 gives up quickly on already-compressed data.
  - 2 TiB is about 70 hours of 1280×720 recording at 489 MB/min.
  - Quota warnings stay at the default 80 %.
- **Permissions**, on each of the three children (**Edit Permissions**):
  - owner user `poringlab`, group `poringlab`;
  - mode `770`;
  - Apply Recursively.

### 1.3 NFS exports (to the VM only)

**Shares → Unix (NFS) Shares → Add**, one per child:

| Path | Hosts | Read only | Mapall user / group |
|---|---|---|---|
| `/mnt/tank-main/poring-lab/datasets` | `192.168.1.13` | no | `poringlab` / `poringlab` |
| `/mnt/tank-main/poring-lab/thai-client-data` | `192.168.1.13` | **yes** | `poringlab` / `poringlab` |
| `/mnt/tank-main/poring-lab/locale-packs` | `192.168.1.13` | no | `poringlab` / `poringlab` |

- **Mapall instead of Maproot.** The lab's tools run as `batt` (uid 1000), not root. Mapall maps
  every client user to `poringlab`, which owns the dataset, so writes work without root on either
  side.
- **The Thai source stays pristine.** The read-only export means the VM can never change it, and
  the VM mounts it `ro` as well.

### 1.4 SMB shares (to the Dell only)

**Shares → Windows (SMB) Shares → Add**:

| Share name | Path | Export read only | Advanced: Hosts Allow / Hosts Deny |
|---|---|---|---|
| `poring-thai-drop` | `/mnt/tank-main/poring-lab/thai-client-data` | no | `192.168.1.169` / `ALL` |
| `poring-locale-packs` | `/mnt/tank-main/poring-lab/locale-packs` | **yes** | `192.168.1.169` / `ALL` |

- Only `poringlab`, and Batt's NAS admin, can authenticate: the datasets are `770 poringlab`.
- **Optional.** **Data Protection → Periodic Snapshot Tasks → Add**:
  - dataset `tank-main/poring-lab/datasets`;
  - daily;
  - lifetime 2 weeks.

  This guards against a mistaken prune.

## 2. The VM: mount points (three sudo lines)

```bash
sudo mkdir -p /mnt/poring-lab-datasets /mnt/poring-thai-src /mnt/poring-locale-packs
printf '%s\n' \
 '192.168.1.6:/mnt/tank-main/poring-lab/datasets         /mnt/poring-lab-datasets nfs _netdev,nofail,x-systemd.automount,nfsvers=4,rw,noatime 0 0' \
 '192.168.1.6:/mnt/tank-main/poring-lab/thai-client-data /mnt/poring-thai-src     nfs _netdev,nofail,x-systemd.automount,nfsvers=4,ro,noatime 0 0' \
 '192.168.1.6:/mnt/tank-main/poring-lab/locale-packs     /mnt/poring-locale-packs nfs _netdev,nofail,x-systemd.automount,nfsvers=4,rw,noatime 0 0' \
 | sudo tee -a /etc/fstab
sudo systemctl daemon-reload && sudo systemctl restart remote-fs.target
```

- **These mounts are never bind-mounted into a container.** An NFS hang must not freeze a lab
  service (quant's NAS-hang incident). Only host-side tools read and write them.
- **`nofail` protects the boot, not the tools.** If the NAS is down, the tools fail instead of
  hanging the VM's boot.

## 3. Windows: copy the Thai data in (Batt, by hand)

1. In poring-lab's session, open Explorer at `\\192.168.1.6\poring-thai-drop`. Log in as
   `poringlab` and tick **Remember my credentials**. That saved credential is what lets the agent
   later read `poring-locale-packs` from its console.
   - The same thing from a console:

         cmdkey /add:192.168.1.6 /user:poringlab /pass

     It prompts for the password, so nothing goes on a command line.
2. Copy `C:\Users\poring-lab\Desktop\ro_thai` into the share, as `\\192.168.1.6\poring-thai-drop\ro_thai`.
3. Copy the WARP Korean msgstringtable extract from `C:\RO-rAthena\_scratch\` into
   `\\192.168.1.6\poring-thai-drop\kro-reference\`. It is the source of the canonical message keys
   (ADR-0012). It is a client asset, and like everything here it is never committed.

**Timing.** 3.3 GB takes about a minute on the LAN. Prefer to avoid quant's evening EOD store step,
which writes to the same NAS.

## 4. Fallback without SMB

Copy `ro_thai` from Batt's Mac with `scp -r` straight to the NAS, if an SSH path exists. Do **not**
stage it through the VM's local disk, which it shares with the quant stack.

## 5. The agent's checks, after Batt says "done"

- `ls` of each mount.
- A write to `/mnt/poring-thai-src` must fail (`Read-only file system`).
- A write, read and delete of a test file in `/mnt/poring-lab-datasets` and
  `/mnt/poring-locale-packs`.
- The ship round-trip (ADR-0010, "Implementation"), outside SET hours (09:30–17:00 Bangkok on
  weekdays; `ship` refuses then, unless `--force-market`):
  1. A 30-second recording on local disk:

         uv run python scripts/record_session.py --backend rdp --label ship-test --seconds 30

     It goes to `/home/batt/poring-lab-rec/<session>/`; the caps are 140 GB free and 20 GB unshipped.
  2. `uv run python scripts/dataset_ship.py status` shows it `local  unshipped` and `nas …: mounted`.
  3. Ship it:

         uv run python scripts/dataset_ship.py ship

     This writes `checksums.sha256`, rsyncs at `--bwlimit=40000` under the quant IO guard,
     re-hashes on the NAS, writes `storage` into the NAS manifest, appends to `INDEX.jsonl`, and
     only then deletes the local copy. It refuses if `/mnt/poring-lab-datasets` is not a mount
     point.
  4. `status` again: the session shows `nas  verified <time>`, and nothing local remains.
     `INDEX.jsonl` has one `shipped` line.
  5. `uv run python scripts/dataset_ship.py prune` is a dry run: nothing is that old yet.
  - Pass: ADR-0010 → ACCEPTED.
  - Pin the test session only if it is worth keeping: `dataset_ship.py pin <id> --reason …`.
- The Thai copy, read only from `/mnt/poring-thai-src`; small extracted files go to `/dev/shm`.
  The 3.3 GB GRF is never copied to the VM.

## Revert

- **NAS:** delete the shares, then the datasets, then the user.
- **VM:** remove the three fstab lines, then
  `sudo systemctl daemon-reload && sudo systemctl restart remote-fs.target`.
- **Windows:** delete the `192.168.1.6` entry in Credential Manager (`cmdkey /delete:192.168.1.6`).
