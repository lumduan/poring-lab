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
- ตั้ง client เป็นแบบหน้าต่าง (windowed) ขนาดพื้นที่เกม 1280 x 720
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

   จะมีหน้าต่าง "bot view" แสดงสิ่งที่บอทเห็นและแผนของมัน
   เพิ่ม `--overlay` เพื่อวาดกรอบทับบนหน้าจอเกมเลย (Windows 10 เวอร์ชัน 2004 ขึ้นไป)

3. **ให้บอทเล่นเอง**

   ```powershell
   uv run simple_bot.py --act --model v1.onnx
   ```

   หน้าต่าง "bot view" เล็ก ๆ จะเปิดขึ้นก่อน จากนั้น **คลิกที่หน้าต่างเกม 1 ครั้งให้อยู่ด้านหน้า** (ภายใน 5 วินาที)
   บอทจะคลิกเฉพาะตอนที่เกมอยู่ด้านหน้าเท่านั้น ดูข้อความในหน้าต่าง PowerShell:
   `the game window is IN FRONT: the bot clicks` = เริ่มเล่นแล้ว
   ถ้าเห็น `... NOT in front ...` ให้คลิกที่หน้าต่างเกมอีกครั้ง
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
| capture | หาหน้าต่างเกมจากชื่อ ("Ragnarok") แล้วจับภาพเฉพาะพื้นที่เกม 1280 x 720 ด้วย `mss` |
| detect | ย่อ/เติมขอบเทา (letterbox) ให้เป็น 1280 x 736 ส่งเข้าโมเดล YOLO (ONNX) แล้วแปลงผลเป็นกรอบ + NMS (ตัดกรอบซ้ำ) |
| decide | state machine: SEARCH (ไม่เห็นมอน: เดินสุ่ม) -> ATTACK (ตีตัวที่ใกล้ที่สุด คลิกซ้ำทุก ~1 วินาที) -> LOOT (มอนหายไป > 1.5 วินาที = ตายแล้ว: คลิกที่เท้ามัน 2 ครั้งเพื่อเก็บของ) -> SEARCH |
| act | ขยับเมาส์ 2 ครั้งก่อนกด (client ไม่รับคลิกที่ "กระโดด" ไปทีเดียว), ไม่คลิกบนหน้าต่าง UI, ไม่คลิกเดินตรงขึ้นเหนือในแนวเดียวกับตัวละคร (client จะไม่ส่งคำสั่งเดิน) |

## ข้อจำกัด

- โมเดลฝึกจากภาพ client ของแล็บที่ 1280 x 720: client อื่น ความละเอียดอื่น หรือซูมกล้องต่างไป อาจหาเจอน้อยลง
- Creamy บินได้ (ภาพลอยเหนือพื้น) มักหาไม่เจอ
- ตำแหน่งหน้าต่าง UI และตำแหน่งตัวละครเป็นค่าคงที่ในโค้ด (หมวด 1 ใน `simple_bot.py`): ถ้าจัดหน้าต่างต่างไป ให้วัดจากภาพหน้าจอแล้วแก้ค่า
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
- **กรอบไม่ตรงตัว**: ตรวจว่าพื้นที่เกมเป็น 1280 x 720 และ Windows display scaling ไม่ได้ทำให้ขนาดเพี้ยน
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
- the client windowed, with a 1280 x 720 game area;
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

   A "bot view" window shows what the bot sees and plans. Add `--overlay` to draw over the game
   itself (Windows 10 version 2004 or later).

3. **Let the bot play**

   ```powershell
   uv run simple_bot.py --act --model v1.onnx
   ```

   A small "bot view" window opens first; then **click the game window once to put it in front**
   (within the 5 s). The bot clicks only while the game is in front. The PowerShell window says
   `the game window is IN FRONT: the bot clicks` when it starts, and `... NOT in front ...` when
   you must click the game again.
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
| capture | finds the client window by title ("Ragnarok") and copies its 1280 x 720 game area with `mss` |
| detect | letterboxes the picture to 1280 x 736 (grey padding), runs the YOLO model (ONNX), turns its output into boxes, NMS removes duplicates |
| decide | a state machine: SEARCH (no monster: wander) -> ATTACK (the nearest one, re-click ~every 1 s) -> LOOT (gone > 1.5 s = dead: click its feet twice to pick up) -> SEARCH |
| act | two mouse motions before each press (the client ignores a "cold jump" click), never on a UI window, never a walk click straight north in the character's own column (the client sends no move for it) |

## Limits

- The model was trained on the lab client's sprites at 1280 x 720: another client, resolution or
  camera zoom can detect worse.
- Creamy flies (its sprite floats above the ground) and is often missed.
- The UI windows and the character's position are constants in the code (section 1 of
  `simple_bot.py`): if your windows sit elsewhere, measure them on a screenshot and change them.
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
- **Boxes are off**: check that the game area is 1280 x 720 and that display scaling does not
  change it.
- **Slow**: the model runs on the CPU, ~0.1-0.5 s per frame; try `--threads 4` or close other
  programs.
