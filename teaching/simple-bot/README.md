# simple-bot: บอทมองภาพ (vision bot) ตัวเล็กสำหรับเรียน image processing ในเกม

> English version below.

## ชุดนี้คืออะไร

`simple_bot.py` เป็นไฟล์ Python ไฟล์เดียว ที่ "มอง" หน้าจอเกม Ragnarok Online แล้ว
ตีกรอบ (box) รอบมอนสเตอร์ ตัดสินใจว่าจะเดินไปไหน และ (ถ้าเปิดโหมด `--act`) คลิกเมาส์ให้เดิน ตี และเก็บของ
บนแผนที่ prt_fild08 (ทุ่งข้างเมือง Prontera: Poring, Lunatic, Fabre, Pupa, Creamy)
มันไม่อ่านหน่วยความจำของเกม และไม่ยุ่งกับข้อมูลเครือข่ายของเกม: ใช้แค่ภาพบนจอ กับเมาส์ เหมือนคนเล่น

ทุกเฟรมผ่าน 4 ขั้น:

```
capture  ->  detect  ->  decide  ->  act
จับภาพ        หากรอบ        ตัดสินใจ      คลิกเมาส์ (เฉพาะ --act)
```

โค้ดเขียนไว้ให้อ่านเรียนรู้ได้: ทุกฟังก์ชันมีคำอธิบาย (ภาษาอังกฤษ) ว่าทำอะไร ทำไม รับ/คืนค่าอะไร

## สิ่งที่ต้องมี

- PC Windows 10/11 หนึ่งเครื่อง
- **Microsoft Visual C++ Redistributable (x64) รุ่นล่าสุด** ติดตั้งครั้งเดียว: https://aka.ms/vs/17/release/vc_redist.x64.exe
  (onnxruntime ต้องใช้รุ่น 14.40 ขึ้นไป ถ้าเก่ากว่านี้ Python จะปิดไปพร้อมข้อความ `access violation`)
- เซิร์ฟเวอร์ rAthena ของตัวเองที่รันบนเครื่องนี้ (local server) และ client Ragnarok ที่ต่อเข้าเซิร์ฟเวอร์นั้น
- client ความละเอียดไหนก็ได้ แบบหน้าต่าง (windowed) ง่ายที่สุด เต็มจอก็ใช้ได้ (ดูหัวข้อ "จอทุกขนาด หน้าต่างหรือเต็มจอ")
- ตัวละครยืนอยู่ที่ prt_fild08
- ไฟล์ในชุดนี้: `simple_bot.py`, `v1.onnx` (โมเดล), โฟลเดอร์ `samples` (ภาพตัวอย่าง 20 ภาพ)
- `v1.onnx` และโฟลเดอร์ `samples` มาพร้อมกันเมื่อ clone branch `teaching-kit` จาก GitHub (`git clone --branch teaching-kit --single-branch https://github.com/lumduan/poring-lab.git simple-bot`) ถ้าได้ไฟล์มาทางอื่นแล้วไม่มีโมเดล ลอง `--detector color` ได้ก่อน

## ติดตั้ง uv (ครั้งเดียว)

เปิด PowerShell แล้วพิมพ์:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

ปิด PowerShell แล้วเปิดใหม่ จากนั้นเข้าโฟลเดอร์ของชุดนี้ เช่น `cd C:\simple-bot`

ครั้งแรกที่รัน `uv run` มันจะโหลด Python และไลบรารีที่ต้องใช้ (numpy, OpenCV, onnxruntime ...)
เองจากอินเทอร์เน็ต (หลายร้อย MB) ครั้งต่อไปจะเร็ว

## ลองใช้ 3 ขั้น

1. **ลองกับภาพตัวอย่าง (ไม่ต้องเปิดเกม)**

   ```powershell
   uv run simple_bot.py --replay samples --model v1.onnx
   ```

   กดปุ่มใดก็ได้เพื่อดูภาพถัดไป กด `q` เพื่อออก
   - เก็บผลเป็นไฟล์ PNG แทนหน้าต่าง: เพิ่ม `--save-dir out`
   - ลองแบบ image processing ดั้งเดิม (หาสีชมพูของ Poring ด้วย HSV ไม่ใช้โมเดล):
     `uv run simple_bot.py --replay samples --detector color`
     ในภาพตัวอย่าง 20 ภาพ วิธีนี้เจอ Poring 21 ตัว ส่วนโมเดลเจอมอนสเตอร์ 47 ตัว (รวม Lunatic, Fabre, Pupa)
     ลองเปรียบเทียบดูว่าวิธีไหนพลาดตรงไหน

2. **ดูเกมจริง แต่บอทไม่กดอะไรเลย**

   ```powershell
   uv run simple_bot.py --watch --model v1.onnx
   ```

   บอทวาดกรอบและเส้นทับบนหน้าจอเกมโดยตรง (overlay: เมาส์คลิกทะลุได้ และไม่แย่งโฟกัสจากเกม;
   Windows 10 เวอร์ชัน 2004 ขึ้นไป) ถ้าอยากดูเป็นหน้าต่างแยก "bot view" ด้วย เพิ่ม `--view on`
   ถ้าวาดทับไม่ได้ (Windows เก่า) บอทจะเปิดหน้าต่าง bot view แทนเอง

3. **ให้บอทเล่นเอง**

   ```powershell
   uv run simple_bot.py --act --model v1.onnx
   ```

   **คลิกที่หน้าต่างเกม 1 ครั้งให้อยู่ด้านหน้า** (ภายใน 5 วินาที) บอทจะคลิกเฉพาะตอนที่เกมอยู่ด้านหน้าเท่านั้น
   ดูข้อความในหน้าต่าง PowerShell: `the game window is IN FRONT: the bot clicks` = เริ่มเล่นแล้ว
   ถ้าเห็น `... NOT in front ...` ให้คลิกที่หน้าต่างเกมอีกครั้ง (อย่าคลิกหน้าต่าง PowerShell ระหว่างเล่น)
   - **เมาส์ไม่ไปตามที่บอทสั่ง (เส้นขึ้น แต่ตัวละครไม่เดิน)**: บอทจะเช็กตำแหน่งเมาส์ก่อนกดทุกครั้ง
     ถ้าเมาส์ไม่ไป จะไม่กด แล้วขึ้นข้อความ `WINDOWS IS NOT LETTING THIS PROGRAM MOVE THE MOUSE` พร้อมสาเหตุ
     ทดสอบด้วย `uv run simple_bot.py --mouse-test` (ขยับเมาส์เฉย ๆ ไม่คลิก) สาเหตุที่พบบ่อย:
     1. เกมรันแบบ "Run as administrator": เปิด PowerShell แบบ "Run as administrator" แล้วรันใหม่
     2. Windows อยู่ในเครื่องเสมือนหรือ remote desktop (เช่น Parallels บน Mac, AnyDesk) ที่ให้เมาส์จริงคุมเคอร์เซอร์:
        ให้เครื่องเสมือนจับเมาส์ไว้ (Parallels: "Optimize for games") หรือใช้ PC Windows จริง
   - กรอบ "monster" คะแนนต่ำ (ต่ำกว่า 0.5) ที่อยู่บนตัวละครเราเอง (ทับเท้าหรือแค่หัว) บอทจะไม่ตี
     (ขึ้นว่า `weak box on our own character`) แลกกับการที่มอนจริงคะแนนต่ำที่ยืนชิดตัวจะถูกข้ามไปด้วย
     และถ้าตีอะไรนาน 20 วินาทีแล้วไม่เกิดอะไร จะเลิกแล้วไม่สนจุดนั้น 15 วินาที
   **หยุด: กด F12 หรือ ดันเมาส์ไปมุมซ้ายบนสุดของจอ** (หยุดเองหลัง 10 นาที; เปลี่ยนได้ด้วย `--minutes`)

## ดู log ว่าบอททำอะไรอยู่ (`--logs`)

เพิ่ม `--logs` ต่อท้ายคำสั่งไหนก็ได้ บอทจะพิมพ์ทีละขั้นพร้อมเวลา ว่าทำถึงไหนแล้วและติดตรงไหน
ถ้าเพิ่ม `--log-file run.log` จะบันทึกลงไฟล์ด้วย (ส่งไฟล์นี้ให้ผู้สอนดูได้)

```powershell
uv run simple_bot.py --act --model v1.onnx --logs --log-file run.log
```

ตัวอย่างสิ่งที่เห็น:

```text
19:03:19.864 INFO    onnxruntime 1.31.1: creating the session for v1.onnx
19:03:20.106 INFO    model loaded in 241 ms: input images [1, 3, 736, 1280], conf 0.25
19:03:20.300 INFO    window found: 'Ragnarok' (hwnd 132456, pid 4321)
19:03:20.410 DEBUG   network check: ['127.0.0.1'] -> ok (1 connection(s), all local)
19:03:25.120 INFO    state start -> ATTACK (new target)
19:03:25.130 DEBUG   frame 12 | ATTACK: new target | boxes 3 (monster 3) | target monster 0.83 | ...
19:03:25.900 INFO    no click at (640, 700): on a UI window or the edge
```

- `INFO` = ขั้นสำคัญ, `DEBUG` = รายละเอียด (สรุปลูปวินาทีละ 1 บรรทัด), `WARNING` = มีอะไรผิดปกติ
- บรรทัด `no click at ...` บอกเหตุผลที่บอทไม่กด เช่น หน้าต่างเกมไม่ได้อยู่ด้านหน้า หรือจุดนั้นอยู่บนหน้าต่าง UI

## จอทุกขนาด หน้าต่างหรือเต็มจอ

บอทปรับตามขนาดพื้นที่เกมเอง (พิมพ์บอกตอนเริ่ม เช่น `client area 1920 x 1080, windowed`)

- **ตัวละคร** อยู่กลางพื้นที่เกมเสมอ (RO วางกล้องไว้ที่ตัวละคร)
- **หน้าต่าง UI** ขนาดเท่าเดิมทุกความละเอียด และติดมุมของมัน: มินิแมพติดขอบขวา หน้าต่างแชตติดขอบล่าง
- **โมเดลดูภาพขนาดจริง** ไม่ย่อไม่ขยาย เพราะ RO วาดตัวละครและมอนสเตอร์ขนาดพิกเซลเท่าเดิมทุกความละเอียด
  (จอใหญ่แค่เห็นโลกกว้างขึ้น) จอใหญ่กว่า 1280 x 736 โมเดลดูเฉพาะกรอบ 1280 x 736 รอบตัวละคร
  (กรอบขาว "model area" ใน bot view) มอนที่ไกลกว่านั้นจะไม่เห็น ซึ่งบอทก็ตีแต่ตัวใกล้อยู่แล้ว
- **เต็มจอ (fullscreen)**: หน้าต่าง bot view จะปิดเอง เพราะหน้าต่างอื่นที่โผล่ทับเกมจะแย่งโฟกัส
  (เกมเต็มจอมักย่อตัวลงไป) ให้ดูข้อความในหน้าต่าง PowerShell หรือใช้ `--logs` แทน ถ้าอยากเปิดจริง ๆ ใช้ `--view on`
- ถ้าขึ้นว่า **`the captured picture is BLACK`** แปลว่าเกมเป็นเต็มจอแบบ exclusive ซึ่งจับภาพหน้าจอไม่ได้:
  เปิด Setup ของ client แล้วเลือกแบบหน้าต่าง (Windowed / Window mode) แล้วรันใหม่

## อ่านภาพ bot view

| สิ่งที่เห็น | ความหมาย |
|---|---|
| กรอบแดง `monster 0.87` | มอนสเตอร์ และความมั่นใจของโมเดล (0-1) |
| กรอบฟ้า `player` / กรอบเขียว `npc` | ผู้เล่นอื่น / NPC: บอทไม่คลิกมอนสเตอร์ที่ทับกับกรอบเหล่านี้ |
| กากบาทสีขาว | เท้าตัวละครของเรา (กลางจอเสมอ) ถ้ามีกรอบ player ทับตรงนี้จะเขียนว่า `self` (โมเดล v1 ฝึกโดยไม่ตีกรอบตัวละครของบอทเอง จึงแทบไม่เห็น) |
| กรอบเทา + เหตุผล | มอนสเตอร์ที่ถูกตัดทิ้ง เช่น อยู่ใต้หน้าต่าง UI |
| กรอบเหลืองหนา + เส้นเหลือง | เป้าหมายที่กำลังตี (ATTACK) |
| เส้นฟ้า | จุดที่เดินสุ่มไปหา (SEARCH) |
| เส้นส้ม | จุดเก็บของ (LOOT) |
| จุดแดง | คลิกในเฟรมนี้ |
| แถบล่าง (HUD) | โหมด, สถานะ, FPS, เวลา ms ของแต่ละขั้น, จำนวนกรอบ |

## แต่ละขั้นทำอะไร

| ขั้น | ทำอะไร |
|---|---|
| capture | หาหน้าต่างเกมจากชื่อ ("Ragnarok") แล้วจับภาพเฉพาะพื้นที่เกม (ขนาดไหนก็ได้) ด้วย `mss` |
| detect | ย่อ/เติมขอบเทา (letterbox) ให้เป็น 1280 x 736 ส่งเข้าโมเดล YOLO (ONNX) แล้วแปลงผลเป็นกรอบ + NMS (ตัดกรอบซ้ำ) |
| decide | state machine: SEARCH (ไม่เห็นมอน: เดินสุ่ม) -> ATTACK (ตีตัวที่ใกล้ที่สุด คลิกซ้ำทุก ~1 วินาที) -> LOOT (มอนหายไป > 1.5 วินาที = ตายแล้ว: คลิกที่เท้ามัน 2 ครั้งเพื่อเก็บของ) -> SEARCH |
| act | ขยับเมาส์ 2 ครั้งก่อนกด (client ไม่รับคลิกที่ "กระโดด" ไปทีเดียว), ไม่คลิกบนหน้าต่าง UI, ไม่คลิกเดินตรงขึ้นเหนือในแนวเดียวกับตัวละคร (client จะไม่ส่งคำสั่งเดิน) |

## ข้อจำกัด

- โมเดลฝึกจากภาพ client ของแล็บ: client อื่น (sprite ต่างไป) หรือซูมกล้องต่างไป อาจหาเจอน้อยลง (ความละเอียดต่างไม่เป็นไร)
- Creamy บินได้ (ภาพลอยเหนือพื้น) มักหาไม่เจอ
- ขนาดหน้าต่าง UI วัดจาก layout ของแล็บ (หมวด 1 ใน `simple_bot.py`): ถ้าจัดหน้าต่างต่างไป ให้วัดจากภาพหน้าจอแล้วแก้ค่า
- บอทนี้ตั้งใจให้เรียบง่าย: ไม่มีแผนที่ ไม่เลี่ยงสิ่งกีดขวาง ไม่ดู HP

## ความปลอดภัย (สำคัญ)

- **ใช้กับเซิร์ฟเวอร์ local ของตัวเองเท่านั้น** `--act` จะคลิกเฉพาะเมื่อ client ต่ออยู่กับ address ในเครื่อง
  (127.0.0.1) หรือในวง LAN (192.168.x.x, 10.x.x.x, 172.16-31.x.x) ทุก connection และตรวจซ้ำทุก 5 วินาที
  ถ้าเจอ address อินเทอร์เน็ต บอทหยุดทันที
- บอทคลิกเฉพาะตอนที่หน้าต่างเกมอยู่ด้านหน้าเท่านั้น
- เซิร์ฟเวอร์ทางการ: การใช้บอทผิดข้อตกลงการใช้งาน (terms of service) และ GameGuard จะบล็อกอยู่แล้ว

## ปัญหาที่พบบ่อย

- **รันแล้วจบเฉย ๆ หรือขึ้น `Windows fatal exception: access violation` ตอนโหลดโมเดล**:
  เครื่องมี Microsoft C++ runtime (`msvcp140.dll`) รุ่นเก่า onnxruntime ต้องใช้รุ่น 14.40 ขึ้นไป
  (ตัวโปรแกรมจะเตือนก่อนโหลดโมเดลถ้าเจอรุ่นเก่า)
  1. ติดตั้ง Microsoft Visual C++ Redistributable (x64) รุ่นล่าสุด: https://aka.ms/vs/17/release/vc_redist.x64.exe
  2. รันใหม่พร้อม `--logs` จะเห็นว่าหยุดที่ขั้นไหน และรุ่นของ `msvcp140.dll`
  3. ดูรหัสจบ: `echo $LASTEXITCODE` (ค่า `-1073741819` = โปรแกรมภาษา C/C++ ล่ม)
  4. ระหว่างนี้ลอง `--detector color` ได้ (ไม่ใช้ onnxruntime)
- **หาหน้าต่างเกมไม่เจอ / เจอหลายหน้าต่าง**: ใส่ชื่อหน้าต่างให้ตรงขึ้น เช่น `--title "Ragnarok"`
- **บอทขยับเมาส์ไม่ได้**: ถ้า client รันแบบ "Run as administrator" ต้องเปิด PowerShell แบบ administrator ด้วย
- **กรอบไม่ตรงตัว / ไม่เจอมอนเลย**: ดูบรรทัด `client area ...` ตอนเริ่ม และกรอบ "model area" ใน bot view ถ้าเปิด `--logs` แล้ว `boxes 0` ตลอดทั้งที่มอนอยู่บนจอ ส่งภาพ bot view ให้ผู้สอนดู
- **ช้า**: โมเดลรันบน CPU ราว 0.1-0.5 วินาทีต่อเฟรม ลอง `--threads 4` หรือปิดโปรแกรมอื่น

---

# simple-bot: a small vision bot for learning image processing in games

## What it is

`simple_bot.py` is ONE Python file that "looks" at the Ragnarok Online screen, draws boxes around
the monsters, decides where to go and (in `--act` mode) clicks the mouse to walk, attack and pick
up loot on prt_fild08 (the field next to Prontera: Poring, Lunatic, Fabre, Pupa, Creamy). It never
reads the game's memory and never touches its network traffic: pixels in, mouse out, like a person.

Every frame goes through four stages:

```
capture  ->  detect  ->  decide  ->  act
pixels       boxes       a plan      mouse clicks (--act only)
```

The code is written to be read: every function says what it does, why, and its inputs and outputs.

## What you need

- one Windows 10/11 PC;
- **the latest Microsoft Visual C++ Redistributable (x64)**, installed once:
  https://aka.ms/vs/17/release/vc_redist.x64.exe (onnxruntime needs 14.40 or newer; with an older
  one Python closes with `access violation`);
- your OWN rAthena server running on that PC (a local server), and a Ragnarok client connected to
  it;
- the client at any resolution; windowed is easiest, fullscreen works too (see "Any screen size,
  windowed or fullscreen");
- your character on prt_fild08;
- this kit: `simple_bot.py`, `v1.onnx` (the model), `samples` (20 example frames).
- `v1.onnx` and `samples` come with a clone of the `teaching-kit` branch on GitHub
  (`git clone --branch teaching-kit --single-branch https://github.com/lumduan/poring-lab.git simple-bot`).
  Got the files another way and no model? Try `--detector color` first.

## Install uv (once)

In PowerShell:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Close and reopen PowerShell, then go to the kit's folder, e.g. `cd C:\simple-bot`.
The first `uv run` downloads Python and the libraries (numpy, OpenCV, onnxruntime ...) by itself
(a few hundred MB); later runs start fast.

## Three steps

1. **Try it on the sample pictures (no game needed)**

   ```powershell
   uv run simple_bot.py --replay samples --model v1.onnx
   ```

   Any key shows the next picture, `q` quits.
   - Save PNGs instead of a window: add `--save-dir out`.
   - Classic image processing (a Poring's pink in HSV, no model):
     `uv run simple_bot.py --replay samples --detector color`
     On the 20 samples it finds 21 Porings; the model finds 47 monsters (Lunatic, Fabre and Pupa
     too). Compare the two: where does each one go wrong?

2. **Watch the live game; the bot presses nothing**

   ```powershell
   uv run simple_bot.py --watch --model v1.onnx
   ```

   The bot draws its boxes and lines straight over the game (the overlay: the mouse passes
   through it and it never takes the focus; Windows 10 version 2004 or later). `--view on` also
   opens a separate "bot view" window; where the overlay cannot work (older Windows), the bot
   view opens by itself instead.

3. **Let the bot play**

   ```powershell
   uv run simple_bot.py --act --model v1.onnx
   ```

   **Click the game window once to put it in front** (within the 5 s). The bot clicks only while
   the game is in front. The PowerShell window says `the game window is IN FRONT: the bot clicks`
   when it starts, and `... NOT in front ...` when you must click the game again (do not click the
   PowerShell window while it plays).
   - **The mouse does not go where the bot sends it (the line shows, the character stays)**: the
     bot reads the cursor before every press; when it did not get there it does NOT press and
     prints `WINDOWS IS NOT LETTING THIS PROGRAM MOVE THE MOUSE` with the causes. Test it with
     `uv run simple_bot.py --mouse-test` (it moves the mouse, never clicks). The usual causes:
     1. the game runs "as administrator": open PowerShell with "Run as administrator", run again;
     2. Windows runs in a virtual machine or a remote desktop (Parallels on a Mac, AnyDesk ...)
        whose cursor follows your real mouse: let the VM capture the mouse (Parallels: "Optimize
        for games"), or use a real Windows PC.
   - A LOW-score (< 0.5) "monster" box on our own character (over the feet, or only the head) is
     never hit (`weak box on our own character`); the price: a weak real monster right next to us
     is skipped too. After 20 s of hitting something with no result the bot gives up and leaves
     that spot alone for 15 s.
   **Stop: press F12, or push the mouse into the screen's top-left corner** (it also stops after
   10 minutes; change it with `--minutes`).

## See what the bot is doing (`--logs`)

Add `--logs` to any command: the bot prints each step with the time, so you see how far it got
and where it is stuck. `--log-file run.log` also writes the lines to a file (send it to your
teacher).

```powershell
uv run simple_bot.py --act --model v1.onnx --logs --log-file run.log
```

- `INFO` = the steps (the model loaded, the window found, every change of state, every click that
  was NOT made and why); `DEBUG` = details (one summary line per second from the loop, each
  network check, each click); `WARNING` = something is off.
- A `no click at ...` line says why the bot did not click: the game window not in front, the
  point on a UI window, the network check.

## Any screen size, windowed or fullscreen

The bot adapts to the game area's size (it says so at the start, e.g. `client area 1920 x 1080,
windowed`):
- **the character** stays at the centre (RO keeps its camera on it);
- **the UI windows** keep their pixel size and stick to their corners: the minimap to the right
  edge, the chat window to the bottom edge;
- **the model sees native scale**, never shrunk or stretched: RO draws sprites at the same pixel
  size at every resolution (a bigger screen only shows more of the world). On a screen bigger than
  1280 x 736 the model looks at the 1280 x 736 around the character (the white "model area" box in
  the bot view); monsters further out are not seen, and the bot only fights near itself anyway;
- **fullscreen**: the bot view turns itself OFF, because any window shown over the game takes the
  focus (a fullscreen game often minimises). Read the PowerShell window or `--logs` instead;
  `--view on` forces the bot view.
- **`the captured picture is BLACK`** means EXCLUSIVE fullscreen, which screenshots cannot see:
  open the client's Setup, choose windowed (Windowed / Window mode), and run again.

## Reading the bot view

| What you see | Meaning |
|---|---|
| red box `monster 0.87` | a monster, and how sure the model is (0-1) |
| blue `player` / green `npc` box | other players / NPCs: the bot never clicks a monster touching them |
| white cross | your character's feet (always at the centre); a player box there says `self` (the v1 model was trained without boxes on the bot's own character, so you will rarely see one) |
| grey box + a reason | a monster left out, e.g. under a UI window |
| thick yellow box + yellow line | the target being attacked (ATTACK) |
| cyan line | the random point it walks to (SEARCH) |
| orange line | the loot point (LOOT) |
| red dot | a click in this frame |
| bottom strip (HUD) | mode, state, FPS, ms per stage, box count |

## What each stage does

| Stage | What it does |
|---|---|
| capture | finds the client window by title ("Ragnarok") and copies its game area (any size) with `mss` |
| detect | letterboxes the picture to 1280 x 736 (grey padding), runs the YOLO model (ONNX), turns its output into boxes, NMS removes duplicates |
| decide | a state machine: SEARCH (no monster: wander) -> ATTACK (the nearest one, re-click ~every 1 s) -> LOOT (gone > 1.5 s = dead: click its feet twice to pick up) -> SEARCH |
| act | two mouse motions before each press (the client ignores a "cold jump" click), never on a UI window, never a walk click straight north in the character's own column (the client sends no move for it) |

## Limits

- The model was trained on the lab client's sprites: another client (other sprites) or another
  camera zoom can detect worse (another resolution is fine).
- Creamy flies (its sprite floats above the ground) and is often missed.
- The UI windows' sizes were measured on the lab's layout (section 1 of `simple_bot.py`): if your
  windows sit elsewhere, measure them on a screenshot and change them.
- On purpose it stays simple: no map, no obstacle avoidance, no HP watching.

## Safety (important)

- **Your own local server only.** `--act` clicks only while EVERY connection of the client goes to
  this PC (127.0.0.1) or your LAN (192.168.x.x, 10.x.x.x, 172.16-31.x.x), re-checked every 5 s;
  an internet address stops the bot at once.
- It clicks only while the game window is in front.
- Official servers: a bot breaks their terms of service, and GameGuard blocks it anyway.

## Common problems

- **It ends with no message, or with `Windows fatal exception: access violation` while loading
  the model**: the PC has an old Microsoft C++ runtime (`msvcp140.dll`); onnxruntime needs 14.40 or
  newer (the script warns before loading the model when it finds an older one).
  1. install the latest Microsoft Visual C++ Redistributable (x64):
     https://aka.ms/vs/17/release/vc_redist.x64.exe;
  2. run again with `--logs`: the last step reached and the `msvcp140.dll` version;
  3. the exit code: `echo $LASTEXITCODE` (`-1073741819` = a crash inside C/C++ code);
  4. meanwhile `--detector color` runs without onnxruntime.
- **The game window is not found / several windows match**: give its title, e.g.
  `--title "Ragnarok"`.
- **The mouse does not move in the game**: if the client runs "as administrator", run PowerShell
  as administrator too.
- **Boxes are off / no monster is ever found**: read the start's `client area ...` line and the
  "model area" box in the bot view; with `--logs`, `boxes 0` all the time while monsters are on the
  screen: send a bot view screenshot to your teacher.
- **Slow**: the model runs on the CPU, ~0.1-0.5 s per frame; try `--threads 4` or close other
  programs.
