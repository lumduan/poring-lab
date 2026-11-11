---
doc_type: design
hypothesis: "A run's and a map's economics can be measured from packets and modelled from the pinned rAthena db at FIXED NPC prices, closely enough to compare maps and setups by ratios (zeny per hour, zeny per weight, payback hours, a Sharpe-like ratio)."
status: ACTIVE (instrumentation built 2026-10-21; prt_fild08 back-filled; orcsdun01 and the candidates modelled; the /economy dashboard built 2026-11-11, section 10; nothing live)
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [../competition.md, ../planning/crusader-build.md, ../planning/orcsdun01-detector.md, ../adr/0007-packet-ground-truth-channel.md]
next_action: "Batt: read section 6 (the measured rows) and section 7 (the map table); decide whether the Crusader's map choice uses the K-free ratios (V per kill, V per HP, V / W) or waits for a measured K on orcsdun01. A one-minute live shop check (section 9) would prove the price rules on the server itself."
title: "Economics: what a run and a map earn at fixed NPC prices (formulas, sources, results)"
date: 2026-10-21
owner: Batt
---

# Economics of a run and of a map (fixed NPC prices)

**Batt, 2026-10-21 (abridged):** "from now on every run also produces an ECONOMIC row, so each test
yields the data for comparing maps and setups by ratios, like P/E or ROE for stocks. Build it
offline first, then attach it to every run; also back-fill it for the banked runs where the
packets allow ... Keep it a model of FIXED NPC prices only: no rares, no player market. Document
the formulas in docs (they double as course material)."

What exists now:

| Piece | File | What it does |
|---|---|---|
| Item table | `scripts/econ_items.py` | NPC sell / buy prices (plain, Overcharge 10, Discount 10), weight, type, shops, for every item, at run time into `data/econ/items.json` (gitignored) |
| Run row | `scripts/econ_row.py` | the per-run ECONOMIC row from packets (section 3), the map model beside it |
| Map model | `scripts/econ_model.py` | per map: expected zeny and weight per kill, the trip to the nearest NPC that buys (or a Kafra), and the ratios (section 4) into `data/econ/maps.json` (gitignored) |
| run_row | `scripts/run_row.py` | the standard row now carries an `economics` block and prints it as a second table; the standard columns are unchanged |
| Survival trials | `scripts/survive_judge.py` | each trial's JSON gains an `economics` entry (costs only) |
| Tests | `services/backend/tests/test_econ.py` | the price rules, the drop rules, the ratios by hand, the trips, the carry split, a synthetic run, and two REAL positive cases (v52 run 1) |
| Dashboard | `scripts/econ_dash.py`, the console's `/economy` page | the counts of banked runs (per run and pooled) at these prices, with prices a person can edit in the browser (section 10) |

```
    econ_items.py build                     # the item table (12 s)
    econ_model.py build                     # the maps (prt_fild08, prt_fild06, orcsdun01 + 6 candidates; ~60 s)
    econ_row.py SID ...                     # rows; --banked prt_fild08 / --trials for a back-fill; --json --pool
    econ_model.py table --L 0.9             # the map comparison (section 7)
    econ_model.py species gef_fild10        # value per kill per species, NPC sell and Overcharge (2026-10-25)
    run_row.py SID ...                      # the standard row + the economics block
    econ_dash.py export SESSION_DIR ... --name NAME   # the /economy page's data (section 10)
```

---

## 1. Sources and rules of the game

- **Server:** PRE-RENEWAL rAthena at `e985006171d2eb320ee512a653f4c83aea3d81b6` (the lab's pin,
  `poring_dataset/mapcache.lock.json`). Every formula below is the `#ifndef RENEWAL` branch.
- **Read at run time, never committed** (GPL-3.0 data, CLAUDE.md rule 4): `db/pre-re/item_db_*.yml`,
  `db/pre-re/mob_db.yml`, `db/pre-re/mob_skill_db.txt`, `db/pre-re/attr_fix.yml`, the map cache, the
  NPC files the map-server loads (`npc/pre-re/scripts_main.conf` and its imports: 522 files, followed
  with `kb_first_workflow.build_world`), `conf/battle/*.conf`. Source citations: `pc.cpp:5689` means
  `src/map/pc.cpp` line 5689 at the pin. `npc.cpp`, `itemdb.cpp`, `conf/battle/items.conf` and
  `conf/battle/player.conf` were fetched at the pin into RAM for this doc.
- **The lab's overrides:** none that touch prices, drops or weights. `services/rathena/conf/import/*.tmpl`
  set no battle option; `conf/import/battle_conf.txt` is the empty template; `db/import` is empty.
  So `conf/battle/drops.conf` holds: every `item_rate_*` 100, every `item_drop_*_min` 1 / `_max` 10000,
  `item_logarithmic_drops: no`, `drop_rateincrease: no`, `drops_by_luk: 0` / `drops_by_luk2: 0`
  (`drops.conf:57-153`), `drop_rate_cap: 9000` (`:209`); `mob_size_influence: no` (`monster.conf:286`).
  The pre-re `map_drops.yml` imports only `db/import` (empty): no map-wide extra drops.
- **Selling needs the trade permission:** the GM group 20 inherits `Player`, whose `can_trade: true`
  (`conf/groups.yml:53` stock; `services/rathena/conf/import/groups.yml`), so `pc_can_give_items`
  (`pc.cpp:1265`) lets both characters on the GM account sell to NPCs.

## 2. The item table (fixed NPC prices)

Per item (`econ_items.py`; `econ_items.py show 504` prints one):

| Field | Meaning | Rule (pinned source) |
|---|---|---|
| `value_buy`, `value_sell` | the item's base prices | the db's `Buy` / `Sell`; a missing `Sell` is `Buy / 2` (integer division), a missing `Buy` is `Sell x 2` (`itemdb.cpp:1185-1188`); if `value_buy / 124 < value_sell / 75`, `Sell` becomes 1, the buy-low / sell-high exploit guard (`itemdb.cpp:1190-1193`) |
| `sell` | what an NPC pays us per unit | `value_sell` x amount (`npc.cpp:3077-3083`); only a plain `shop` NPC buys (`npc.cpp:3040`); a `Trade: NoSell` item cannot be sold (`pc.cpp:1307`, `itemdb_cansell`): 0 |
| `sell_oc10` | the same with **Overcharge lv 10** | `pc_modifysellvalue` (`pc.cpp:5708-5719`): rate = 5 + 2L - (L == 10) = **24 %**; per unit `(int32)(value_sell x 124 / 100.)`, a C double **truncated** toward zero, then `max(min_shop_sell = 0)` (`items.conf:138`) |
| `npc_buy` | the cheapest loaded shop's price | the shop line's price, or `value_buy` when it says `-1` (`npc.cpp:4146-4148`) |
| `npc_buy_dc10` | the same with **Discount lv 10** | `pc_modifybuyvalue` (`pc.cpp:5689-5703`): 24 % at lv 10; per unit `(int32)(price x 76 / 100.)`, truncated, then `max(min_shop_buy = 1)` (`items.conf:134`); only in a shop whose discount flag is on (`npc.cpp:2875-2876`, `npc_shop_discount` 4251-4260). A plain `shop` line is discountable unless its first entry is `no` (`npc.cpp:4091-4105`) |
| `weight` | in-game weight per unit | the db's `Weight / 10` (10 db units = 1) |

**Rounding is per UNIT, then x amount** (`npc.cpp:2875-2879` buy, `:3080-3083` sell). So the skills
gain nothing on cheap loot: Jellopy sells for 3 (`Buy: 6`, `item_db_etc.yml:652-657`), and 3 x 1.24 =
3.72 truncates back to **3**; Clover 5 -> 6, Red Herb 9 -> 11; a White Potion sells for 600 -> **744**
and costs 1,200 -> **912** with Discount 10 (`item_db_usable.yml:116`). Neither skill belongs to our
characters (Merchant skills): the `_oc10` / `_dc10` columns are the "what if a Merchant sold / bought"
benchmark Batt asked for.

The table covers all 6,169 pre-re items and the 186 loaded `shop` NPCs (no floating shops), with
each item's `drops_on` (map -> the species that drop it). The Crusader's shop gear (crusader-build.md
4a) costs **310,000** at the cheapest shops (**235,600** with Discount 10), matching that doc.

## 3. The per-run ECONOMIC row (measured, from packets)

`econ_row.py` (pure `measure()` + loaders). Packets are offline ground truth (ADR-0007); nothing here
reaches a bot. Every symbol:

| Symbol | Definition | Packets / source |
|---|---|---|
| `h` | the judged window in hours | a bot run: its first walk after the loop start to its last click + 5 s; Batt's demo: 600 s from his first walk (`search_study.load_session`, the same window run_row's kills / h use); a survival trial: its manifest's `t0_ns..t1_ns` |
| `n` | our kills in the window | `arm_judge.kills_of`: a monster's death vanish <= 1.5 s after OUR damaging hit |
| `K` | kills per hour | `n / h` (equals flow_judge's kills / h: v52 run 1 102.0 both) |
| `D_k` | the drops of kill k | `arm_judge.drops_of_kill` (fell -0.6..+1.5 s around the death, <= 4 cells) via `loot_complete.kill_rows`; each floor item i has amount `a_i` (its fall packet), sell `s_i`, OC sell `s_i^OC`, weight `w_i` |
| fate | picked / left behind / looter / expired / left / gone | `arm_judge.item_fates`: picked = our `pickup_request` answered ok |
| `Z_drop`, `Z_pick` | zeny dropped / picked | `sum a_i s_i` over all `D_k` / over the picked ones |
| `V_theor` | zeny DROPPED per kill (the theoretical V) | `Z_drop / n` |
| `V` | zeny PICKED per kill (realised, mark-to-market) | `Z_pick / n` (`V_oc` with `s^OC`) |
| `L` | loot completeness BY VALUE | `Z_pick / Z_drop`; also by count (`L_count`) and NET of re-drops (`L_net`: a looter's re-drop of our own item is the same item, counted once: `loot_complete.link_redrops`) |
| carry | what a LOOTER monster carried and re-dropped at its death | section 3a |
| `W`, `W_theor` | weight picked / dropped per kill | `sum a_i w_i / n` |
| `V / W` | zeny per weight unit | `Z_pick / sum_picked a_i w_i` |
| consumables | our item uses at NPC prices | OUR `use_item_result` successes (a success is broadcast to the area: filtered by our id 2000002); potion = item type Healing, Fly Wing 601, Butterfly Wing 602, other; cost = the cheapest NPC price (`cost_dc` with Discount 10); an item no NPC sells is left out, with the reason |
| deaths / h | our deaths | our own id's vanish with reason 1 (died) (`survive_judge.deaths_of`) |
| `G` | gross zeny per hour | `Z_pick / h` = `K x V`; `G_oc` with OC |
| `c` | consumables per hour | `cost / h` |
| `N` | net zeny per hour | `G - c`; "best" = OC sells and DC buys |
| cost ratio | | `cost / Z_pick` |
| windows | the zeny of each FULL 10-min window from the start | pickups booked at their pickup time, costs at their use time, x 6 = zeny / h per window |
| Sharpe-like | | mean / sample standard deviation of those windows (needs >= 2 windows: a 10-min demo has one, so None) |
| `C`, `w_0` | capacity and the weight carried at the start | the `max_weight` and `weight` stat packets in force at the window's start, / 10 (STR 99 Novice GM: 20000 + 99 x 300 = 49700 db units = 4970, `status.cpp:3663`; the Crusader 4150) |
| fill time | hours to reach x % of C at this run's weight rate | `(x C - w_0) / (K x W)`, at x = 50 % (natural and skill regen stop: `natural_heal_weight_rate` 50, the pre-re default, `battle.cpp:8393-8395`) and 90 % (no attacks: `major_overweight_rate: 90`, `player.conf:77`). **50 % is the one the model's u uses.** |

Missing data is `None` with the reason in `why` -- never invented.

### 3a. Looter carry (found while building this; it changes how V is read)

Porings (and Drops) are LOOTERS (mob_db `Ai: 02` = `MONSTER_TYPE_02 = 0x83`, bit 0x2 = looter,
`mob.hpp:153`). A looter picks up items lying on the floor -- including what our bot left behind --
and drops them again when it dies, AFTER its own drops (`mob.cpp:2556-2571`: the regular list, then
the looted list; a looted stack keeps its amount). A monster's own drops are one unit each
(`mob_setdropitem(entry, 1, ...)`, `mob.cpp:3343`), one per drop-list entry at most, in drop-list
order. So per kill, `split_carry` takes the longest prefix of its drops (creation = floor-id order)
that fits the species' drop list in order, one unit each; and as many items as `link_redrops` linked
to our own earlier items (re-drops) are cut from the END (the looted list comes last; the link may
name the own copy of the same item id, so the count is used, not the position). The rest is CARRY.
It is a LOWER bound on carry (a carried single item that happens to fit the order counts as own).

The model compares OWN drops; carry is reported apart (`V_carry`). Without the split, v52 run 1's
Porings showed 1.25 items per kill against the model's 1.017 (Clover from a Poring is impossible
from its own list). The Lunatic, not a looter, matched without any split (section 6c).

## 4. The map model (expected values from the db)

`econ_model.py`. Per species s and drop entry i:

- **Drop chance** `p_i = r_i / 10000`, `r_i` the effective rate. At db load (`mob.cpp:6847-6905`):
  `+1` if `drop_rateincrease` and the rate < 5000; the class multiplier `item_rate_<class>[_boss|_mvp]`
  by item type (Healing -> heal; Usable / Cash -> use; Weapon / Armor / PetArmor -> equip; Card ->
  card; anything else common: the switch at `:6862-6893`), a treasure chest's own rate, then
  `mob_drop_adjust` (`:4808-4820`: linear, or logarithmic when enabled) clamped to the class's
  `[min, max]`. At the kill, `mob_getdroprate` (`:2818-2889`): size influence, LUK, the killer's drop
  bonuses (none on our gear: 100 %; the 90 % cap only bites a bonus), `min(10000)`, `max(1)`. The roll
  is `rnd() % 10000 >= rate` -> no drop (`:3335`). **On our server this is mob_db's Rate, clamped to
  [1, 10000]** (`effective_rate`; the test pins the other branches).
- **Rares are out of V** (Batt: "no rares"): base rate <= 10 (0.10 %), every Card, every PetEgg (an egg
  goes straight into the killer's inventory, never on the floor: `mob.cpp:3338-3341`). Their expected
  NPC value is reported as `rare_v`. MVP drops are never in V.
- `V_s = sum_i p_i s_i` (zeny per kill dropped), `W_s = sum_i p_i w_i`. `V = V_core + V_tail`:
  `V_core` the drops at >= 1 %, `V_tail` the rest (0.1-1 %): a typical run sees `V_core`; the mean
  includes `V_tail`, which a one-hour run may or may not hit (one Rainbow Carrot, 1,250 z, is 77 % of
  v51 run 1's revenue: section 6c).
- **Kill mix** `pi_s`: the map's normal spawn lines' amounts (boss lines listed, not farmed; a
  metamorphosis target such as prt_fild08's Pupa -> Creamy is in the species list for measured
  mixes), or a run's measured kills. `V = sum_s pi_s V_s`, `W = sum_s pi_s W_s`.
- **Trip** `T` (round trip, seconds): from a uniformly random walkable cell of the farm map to the
  nearest NPC that buys (a placed `shop`) or the nearest Kafra (storage), whichever resets the bag
  sooner, and back. Walking only: Dijkstra over the server's map cache (`poring_dataset.mapcache`,
  lock-checked) at 150 ms per cell (`DEFAULT_WALK_SPEED`, `mmo.hpp:93`), x 1.4 on a diagonal
  (`unit.cpp:228-231`), a diagonal needing both orthogonal cells free; portals by their trigger area
  (`npc.cpp:4994-4999`) + 2 s per map change; "transport" NPC warps (no variable test, e.g. a
  dungeon's entrance NPC) + 3 s of dialog; Kafra teleports and quest-gated warps are left out. The
  NPC is used from within 3 cells (the server allows 15: `npc.cpp:2158-2161`). 20 s at the NPC. A
  Kafra charges its storage fee once per trip (`callfunc "F_Kafra"`'s 4th argument,
  `npc/kafras/kafras.txt:10-16`). The return is assumed to cost the same. Butterfly / Fly Wings are
  not modelled.
- **The ratios** (`ratios()`, all per hour):
  - `G = K x L x V` (gross per farming hour), weight rate `K x L x W`;
  - fill time `F = C / (K x L x W)`, `C` the free capacity at 50 % (default: the Crusader's
    0.5 x 4150 - 920 gear = 1,155);
  - farming-time share `u = F / (F + T)`;
  - **net per wall-clock hour** `N = u x (G - c) - fee / (F + T)`;
  - cost ratio `c / G`; zeny per weight `V / W`;
  - **payback hours** (the P/E analogue: price / earnings per period) `= gear cost / N`;
  - **N / gear** (the ROE analogue: earnings per period / capital), per hour;
  - **Sharpe-like** (10-min windows): kills per window `~ Poisson(n = K / 6)`, each drop picked
    independently with probability `p_i L` (compound Poisson): mean `n L V - c / 6`, variance
    `n E[X^2]` with `E[X^2] = sum q_i v_i^2 + (sum q_i v_i)^2 - sum q_i^2 v_i^2`, `q_i = p_i L`;
    ratio = mean / sd;
  - deaths / h: measured only.

## 5. A ROUGH kill rate for the Crusader (`K_est`; only where no run measured K)

`K_est = 3600 / (s + sum_s pi_s HP_s / DPS_s)`, `s = 10 s` of search / approach per kill (Batt's
prt_fild08 demo: 12.0 s per kill, ~2 s of it killing). `DPS_s` = hit chance x mean hit damage / 0.730 s,
for the MAIN build of crusader-build.md 3e (Flamberge ATK 150, weapon level 3, DEX 23, HIT 83, batk 82):
weapon roll ~ U[min(DEX x 1.4, 150), 150) x the 1-hand-sword size fix (Small 75 / Medium 100 / Large 75,
`db/size_fix.yml`) + batk, x the Neutral -> element fix (`db/pre-re/attr_fix.yml`), x (100 - DEF) / 100,
- (VIT + E[rnd(0, (VIT / 20)^2 - 1)]) (`battle.cpp:4825-4832`), + Sword Mastery 40, + Demon Bane 60 on
Undead race / element or Demon race (`battle.cpp:2291-2294`); a plant (IgnoreMelee) takes 1 per hit;
hit = clamp(80 + 83 - (level + AGI), 5, 100) %; crits ignored. Orc Zombie: ~252 per hit, 329 per s
(crusader-build.md: ~240 / 329). **It ignores being swarmed, healing stops and deaths: it is a
ranking aid, not a forecast.**

---

## 6. Results: the measured rows (back-filled 2026-10-21)

All numbers in this section are OUR measurements from the banked packets
(`econ_row.py --banked prt_fild08 --json --pool`, `--banked prt_fild06`, `--trials`, and Batt's demo
`20261016T093835-demo-human-demo`; run 2026-10-21 20:29-20:31 ICT, every session in
`/dev/shm/poring-lab-demo`). The disk archive (`/home/batt/poring-lab-shm-archive`, MANIFEST.tsv
read, no session file read) holds no hunt run, no human demo and no shop packet: nothing there could
add to the back-fill. Prices: the item table of section 2.

### 6a. prt_fild08: every banked hunt run, pooled per version

95 runs with a flow_judge.json (v1-v53; v19 and v45-v47 have none banked), 82.1 hours, 9,973 kills.
Pooled = sums of kills, zeny, weight and hours, the ratios re-taken from the sums; the Sharpe-like
ratio pools every run's 10-min windows. Costs and deaths are 0 in every run (the Novice GM is immune
and uses no item), so net = gross.

| version | runs | hours | kills | K / h | V picked z/kill (OC) | V_theor | carry z/kill | L by value | W / kill | V / W | gross z/h | Sharpe-like (windows) | model err: V own / V core / W |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| v1 | 1 | 0.50 | 20 | 40.3 | 0.00 (0.00) | 8.20 | 1.80 | 0.0 % | 0.00 | - | 0.0 | - (2) | -13.2 % / 10.9 % / -9.4 % |
| v2 | 1 | 0.50 | 13 | 26.0 | 0.00 (0.00) | 5.15 | 0.00 | 0.0 % | 0.00 | - | 0.0 | - (3) | -36.3 % / -19.2 % / -11.7 % |
| v3 | 1 | 0.50 | 20 | 40.0 | 0.15 (0.15) | 5.45 | 0.90 | 2.8 % | 0.05 | 3.00 | 6.0 | 0.58 (3) | -35.0 % / -18.2 % / -11.2 % |
| v4 | 1 | 0.30 | 12 | 39.3 | 0.25 (0.25) | 3.42 | 1.08 | 7.3 % | 0.08 | 3.00 | 9.8 | - (1) | -52.8 % / -59.1 % / -36.0 % |
| v5 | 2 | 1.00 | 83 | 83.0 | 0.19 (0.22) | 6.24 | 1.88 | 3.1 % | 0.05 | 4.00 | 16.0 | 0.70 (5) | -39.5 % / -23.3 % / -24.6 % |
| v6 | 1 | 0.50 | 56 | 112.7 | 0.25 (0.27) | 7.07 | 1.95 | 3.5 % | 0.07 | 3.50 | 28.2 | 0.71 (2) | -29.0 % / -9.9 % / -10.2 % |
| v7 | 1 | 0.65 | 52 | 80.3 | 0.19 (0.21) | 10.94 | 3.15 | 1.8 % | 0.06 | 3.33 | 15.4 | 0.58 (3) | 3.2 % / 32.7 % / -5.5 % |
| v8 | 2 | 0.54 | 28 | 51.9 | 0.00 (0.00) | 8.64 | 0.82 | 0.0 % | 0.00 | - | 0.0 | - (3) | -1.8 % / 28.0 % / 11.9 % |
| v9 | 1 | 0.41 | 27 | 66.4 | 0.19 (0.22) | 6.22 | 0.41 | 3.0 % | 0.04 | 5.00 | 12.3 | 0.71 (2) | -21.2 % / 0.7 % / -36.1 % |
| v10 | 1 | 1.00 | 136 | 135.9 | 0.28 (0.30) | 8.64 | 3.47 | 3.2 % | 0.08 | 3.45 | 38.0 | 1.68 (6) | -29.1 % / -10.1 % / -15.3 % |
| v11 | 1 | 1.00 | 138 | 137.9 | 1.22 (1.41) | 10.62 | 4.97 | 11.5 % | 0.19 | 6.46 | 167.9 | 1.53 (6) | 45.1 % / -4.1 % / 81.4 % |
| v12 | 1 | 0.62 | 109 | 176.0 | 1.08 (1.25) | 10.82 | 4.17 | 10.0 % | 0.57 | 1.90 | 190.6 | 4.90 (3) | -7.6 % / 17.1 % / 21.4 % |
| v13 | 1 | 1.00 | 172 | 171.9 | 0.60 (0.65) | 8.08 | 2.32 | 7.4 % | 0.18 | 3.32 | 102.9 | 2.03 (6) | -25.0 % / -6.8 % / -8.8 % |
| v14 | 1 | 1.00 | 165 | 164.9 | 0.22 (0.25) | 9.88 | 3.28 | 2.2 % | 0.06 | 3.60 | 36.0 | 0.51 (6) | -12.3 % / 10.0 % / 33.7 % |
| v15 | 1 | 1.00 | 143 | 142.9 | 0.95 (1.03) | 7.92 | 2.96 | 12.0 % | 0.28 | 3.40 | 135.9 | 2.56 (6) | -29.6 % / -11.3 % / -0.3 % |
| v16 | 2 | 0.83 | 70 | 83.9 | 0.73 (0.86) | 9.31 | 1.53 | 7.8 % | 0.09 | 8.50 | 61.1 | 0.67 (4) | 1.4 % / 30.9 % / -16.0 % |
| v17 | 1 | 1.00 | 95 | 94.9 | 1.60 (1.83) | 18.28 | 7.18 | 8.8 % | 0.36 | 4.47 | 151.9 | 1.18 (6) | 46.8 % / -0.8 % / -13.5 % |
| v18 | 1 | 1.00 | 98 | 98.0 | 2.30 (2.58) | 8.76 | 1.62 | 26.2 % | 0.52 | 4.41 | 225.1 | 2.37 (5) | 1.4 % / 27.8 % / -4.1 % |
| v20 | 2 | 1.75 | 223 | 127.5 | 1.44 (1.57) | 15.15 | 3.81 | 9.5 % | 0.44 | 3.29 | 184.1 | 1.38 (10) | 55.6 % / 0.1 % / 10.6 % |
| v21 | 1 | 1.00 | 101 | 100.8 | 2.22 (2.54) | 8.24 | 2.51 | 26.9 % | 0.41 | 5.46 | 223.6 | 1.54 (6) | -24.2 % / -2.7 % / -19.2 % |
| v22 | 1 | 1.00 | 124 | 123.5 | 1.25 (1.40) | 11.86 | 1.78 | 10.5 % | 0.37 | 3.37 | 154.4 | 1.70 (6) | 31.6 % / 1.9 % / -3.6 % |
| v23 | 1 | 0.43 | 62 | 145.2 | 1.98 (2.21) | 7.08 | 2.56 | 28.0 % | 0.56 | 3.51 | 288.1 | 9.43 (2) | -40.6 % / -23.5 % / 4.3 % |
| v24 | 1 | 1.00 | 147 | 146.9 | 3.85 (4.35) | 21.41 | 6.69 | 18.0 % | 1.14 | 3.39 | 565.5 | 1.94 (6) | 103.0 % / 8.9 % / 13.4 % |
| v25 | 1 | 1.00 | 110 | 109.9 | 3.74 (4.25) | 6.20 | 0.74 | 60.3 % | 1.27 | 2.94 | 410.7 | 3.60 (6) | -26.8 % / -10.1 % / 4.1 % |
| v26 | 1 | 0.65 | 84 | 129.1 | 5.56 (6.14) | 26.39 | 5.64 | 21.1 % | 1.39 | 3.99 | 717.6 | 1.64 (3) | 183.5 % / 2.3 % / 15.2 % |
| v27 | 1 | 0.48 | 68 | 141.7 | 3.97 (4.47) | 44.69 | 39.50 | 8.9 % | 1.01 | 3.91 | 562.6 | 1.67 (2) | -28.3 % / -8.9 % / -15.5 % |
| v28 | 1 | 1.00 | 142 | 141.9 | 3.18 (3.57) | 8.58 | 3.45 | 37.1 % | 1.10 | 2.90 | 451.7 | 4.52 (6) | -29.6 % / -10.5 % / 6.6 % |
| v29 | 1 | 1.00 | 132 | 131.9 | 6.76 (7.56) | 16.16 | 10.95 | 41.8 % | 1.78 | 3.80 | 891.1 | 0.70 (6) | -27.1 % / -7.8 % / -19.2 % |
| v30 | 1 | 1.00 | 105 | 105.0 | 2.61 (2.87) | 5.68 | 0.87 | 46.0 % | 0.75 | 3.47 | 274.0 | 1.67 (6) | -32.4 % / -14.6 % / 23.0 % |
| v31 | 1 | 0.75 | 76 | 101.3 | 4.66 (5.28) | 8.34 | 4.01 | 55.8 % | 1.78 | 2.62 | 471.7 | 1.09 (4) | -43.7 % / -32.9 % / 0.2 % |
| v32 | 2 | 1.18 | 167 | 141.5 | 4.84 (5.50) | 8.68 | 1.99 | 55.8 % | 1.13 | 4.28 | 685.5 | 1.44 (7) | -9.2 % / 15.8 % / 2.1 % |
| v33 | 3 | 2.15 | 273 | 126.9 | 4.38 (4.88) | 10.85 | 4.98 | 40.4 % | 1.10 | 3.99 | 555.8 | 1.74 (12) | -23.2 % / -2.7 % / -5.7 % |
| v34 | 2 | 2.00 | 262 | 131.3 | 3.51 (3.94) | 6.22 | 0.79 | 56.5 % | 1.16 | 3.04 | 460.9 | 3.47 (11) | -25.4 % / -5.2 % / -0.2 % |
| v35 | 2 | 2.00 | 281 | 140.4 | 3.63 (4.08) | 10.12 | 2.93 | 35.9 % | 1.08 | 3.37 | 509.5 | 1.74 (12) | 31.4 % / -6.0 % / 61.1 % |
| v36 | 2 | 2.00 | 304 | 151.8 | 3.37 (3.76) | 8.37 | 0.90 | 40.2 % | 1.04 | 3.25 | 511.3 | 2.70 (12) | 2.0 % / -14.0 % / 2.0 % |
| v37 | 1 | 1.00 | 141 | 141.0 | 4.58 (5.22) | 8.50 | 1.91 | 53.9 % | 0.96 | 4.75 | 645.9 | 2.53 (6) | -8.7 % / 14.2 % / -12.6 % |
| v38 | 4 | 4.00 | 539 | 134.6 | 3.82 (4.30) | 10.64 | 3.92 | 35.9 % | 1.13 | 3.39 | 514.8 | 1.75 (23) | -5.6 % / 2.0 % / 1.5 % |
| v39 | 4 | 4.00 | 605 | 151.1 | 4.34 (4.84) | 8.17 | 2.81 | 53.1 % | 1.33 | 3.27 | 656.3 | 0.91 (24) | -27.7 % / -8.7 % / -2.4 % |
| v40 | 4 | 4.00 | 510 | 127.4 | 3.58 (3.98) | 11.88 | 4.55 | 30.1 % | 0.97 | 3.67 | 455.8 | 1.49 (24) | -1.9 % / -8.1 % / -13.7 % |
| v41 | 4 | 3.60 | 537 | 149.1 | 4.16 (4.80) | 10.70 | 4.08 | 38.9 % | 0.90 | 4.62 | 620.5 | 0.85 (20) | -10.8 % / -2.1 % / -4.6 % |
| v42 | 4 | 4.00 | 520 | 129.9 | 4.76 (5.45) | 11.32 | 4.13 | 42.0 % | 1.57 | 3.04 | 618.3 | 1.39 (24) | -5.0 % / 5.7 % / 15.7 % |
| v43 | 4 | 3.90 | 388 | 99.5 | 2.86 (3.25) | 8.01 | 1.84 | 35.8 % | 0.84 | 3.39 | 284.9 | 1.35 (23) | -16.6 % / 6.5 % / -0.4 % |
| v44 | 4 | 3.67 | 374 | 101.9 | 5.26 (6.16) | 10.34 | 1.21 | 50.8 % | 1.13 | 4.66 | 535.8 | 0.87 (20) | 21.2 % / 10.0 % / -2.0 % |
| v48 | 4 | 4.00 | 399 | 99.7 | 4.44 (5.03) | 9.07 | 3.18 | 48.9 % | 1.08 | 4.11 | 442.8 | 1.16 (23) | -18.4 % / 3.6 % / -12.6 % |
| v49 | 5 | 4.18 | 567 | 135.8 | 3.21 (3.60) | 7.66 | 2.02 | 41.9 % | 0.96 | 3.33 | 435.4 | 2.59 (25) | -24.6 % / -3.4 % / -2.0 % |
| v50 | 4 | 4.00 | 365 | 91.2 | 5.15 (5.82) | 7.47 | 1.47 | 68.9 % | 1.42 | 3.64 | 469.7 | 0.91 (24) | -21.7 % / 1.1 % / 7.0 % |
| v51 | 4 | 4.00 | 382 | 95.5 | 10.77 (12.74) | 12.04 | 1.71 | 89.4 % | 1.82 | 5.92 | 1,028.4 | 0.62 (23) | 37.3 % / -2.5 % / 2.5 % |
| v52 | 3 | 3.00 | 397 | 132.3 | 5.99 (6.83) | 7.18 | 0.77 | 83.4 % | 1.83 | 3.27 | 792.3 | 2.49 (18) | -12.3 % / 5.5 % / 17.6 % |
| v53 | 1 | 1.00 | 151 | 151.0 | 5.31 (6.12) | 6.56 | 1.17 | 81.0 % | 1.92 | 2.77 | 801.9 | 2.63 (6) | -27.8 % / -21.0 % / -4.5 % |
| **all 95 runs** | 95 | 82.11 | 9,973 | 121.5 | 3.84 (4.36) | 10.07 | 3.16 | 38.1 % | 1.03 | 3.71 | 466.0 | 0.81 (472) | -4.8 % / -1.1 % / 2.8 % |
| v48-v53 | 21 | 20.18 | 2,261 | 112.0 | 5.65 (6.49) | 8.46 | 1.81 | 66.7 % | 1.42 | 3.98 | 632.5 | 0.76 (119) | -10.6 % / -0.9 % / 1.6 % |

### 6b. The latest runs one by one, Batt's demo, and the held-out prt_fild06

| run | kills | K / h | V picked (OC) | V_theor | carry z/kill | L value (count) [net] | W / kill | V / W | gross z/h | 10-min z/h mean ± sd (n) | Sharpe-like | fill h 50 % / 90 % (w0) | model V own: meas vs model (err) | model V core (err) | model gross z/h (err) | model Sharpe |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 20261020T093755 v48 | 110 | 110.0 | 2.60 (2.89) | 5.81 | 0.77 | 44.8 % (46.9 %) [51.0 %] | 0.76 | 3.40 | 286.0 | 301.2 ± 92.1 (5) | 3.27 | 23.2 / 46.8 (538) | 5.04 vs 7.30 (-31.0 %) | 5.04 vs 5.74 (-12.2 %) | 359.6 (-20.5 %) | 0.54 |
| 20261020T104057 v48 | 108 | 108.0 | 4.01 (4.54) | 7.38 | 1.31 | 54.3 % (50.0 %) [64.0 %] | 0.93 | 4.33 | 432.9 | 433.0 ± 216.8 (6) | 2.00 | 19.4 / 39.3 (546) | 6.06 vs 7.17 (-15.4 %) | 6.06 vs 5.66 (7.2 %) | 420.5 (2.9 %) | 0.60 |
| 20261020T114234 v48 | 89 | 89.0 | 5.31 (6.03) | 11.93 | 5.62 | 44.5 % (48.9 %) [47.5 %] | 1.28 | 4.15 | 472.8 | 473.0 ± 351.1 (6) | 1.35 | 17.0 / 34.4 (552) | 6.31 vs 7.16 (-11.8 %) | 6.31 vs 5.65 (11.7 %) | 283.7 (66.6 %) | 0.50 |
| 20261020T124405 v48 | 92 | 91.9 | 6.30 (7.21) | 12.20 | 5.87 | 51.7 % (52.6 %) [54.6 %] | 1.45 | 4.36 | 579.4 | 580.0 ± 673.8 (6) | 0.86 | 14.5 / 29.5 (554) | 6.33 vs 7.26 (-12.8 %) | 6.33 vs 5.71 (10.8 %) | 344.7 (68.1 %) | 0.53 |
| 20261020T135303 v49 | 18 | 104.8 | 3.67 (3.94) | 6.78 | 0.39 | 54.1 % (61.5 %) [57.4 %] | 1.28 | 2.87 | 384.3 | 396.0 ± - (1) | - | 14.4 / 29.2 (558) | 6.39 vs 7.48 (-14.5 %) | 6.39 vs 5.83 (9.7 %) | 423.9 (-9.3 %) | 0.59 |
| 20261020T140632 v49 | 142 | 141.9 | 3.30 (3.69) | 10.46 | 4.42 | 31.5 % (37.5 %) [50.4 %] | 0.85 | 3.87 | 467.6 | 468.0 ± 226.3 (6) | 2.07 | 15.9 / 32.4 (560) | 6.05 vs 7.48 (-19.2 %) | 6.05 vs 5.84 (3.6 %) | 334.4 (39.8 %) | 0.50 |
| 20261020T151005 v49 | 119 | 118.9 | 3.68 (4.21) | 7.03 | 1.13 | 52.4 % (50.3 %) [61.2 %] | 1.45 | 2.53 | 437.6 | 438.0 ± 201.7 (6) | 2.17 | 11.1 / 22.6 (568) | 5.89 vs 7.56 (-22.1 %) | 5.89 vs 5.88 (0.2 %) | 470.7 (-7.0 %) | 0.59 |
| 20261020T161139 v49 | 154 | 153.9 | 2.94 (3.29) | 6.73 | 1.58 | 43.6 % (45.5 %) [55.7 %] | 0.78 | 3.77 | 451.6 | 452.0 ± 165.1 (6) | 2.74 | 16.0 / 32.5 (572) | 5.16 vs 7.47 (-31.0 %) | 5.16 vs 5.83 (-11.5 %) | 501.0 (-9.9 %) | 0.62 |
| 20261020T171325 v49 | 134 | 133.8 | 2.94 (3.26) | 6.43 | 1.01 | 45.7 % (48.3 %) [53.5 %] | 0.81 | 3.61 | 393.5 | 394.0 ± 115.6 (6) | 3.41 | 17.5 / 35.8 (578) | 5.43 vs 7.41 (-26.8 %) | 5.43 vs 5.80 (-6.4 %) | 453.5 (-13.2 %) | 0.59 |
| 20261020T183131 v50 | 99 | 98.9 | 7.74 (8.69) | 10.22 | 4.30 | 75.7 % (64.8 %) [79.3 %] | 1.97 | 3.93 | 765.4 | 766.0 ± 992.6 (6) | 0.77 | 9.8 / 20.0 (582) | 5.92 vs 7.53 (-21.4 %) | 5.92 vs 5.86 (1.0 %) | 563.6 (35.8 %) | 0.65 |
| 20261020T193309 v50 | 85 | 84.9 | 5.26 (6.00) | 7.29 | 0.26 | 72.1 % (77.7 %) [72.9 %] | 1.73 | 3.04 | 446.6 | 447.0 ± 122.3 (6) | 3.65 | 12.9 / 26.4 (590) | 7.04 vs 7.76 (-9.3 %) | 7.04 vs 5.99 (17.4 %) | 474.8 (-5.9 %) | 0.57 |
| 20261020T203445 v50 | 69 | 68.9 | 3.28 (3.71) | 6.84 | 0.30 | 47.9 % (55.2 %) [50.1 %] | 0.84 | 3.90 | 225.8 | 226.0 ± 120.3 (6) | 1.88 | 32.6 / 66.9 (598) | 6.54 vs 7.79 (-16.0 %) | 6.54 vs 6.01 (8.8 %) | 256.8 (-12.1 %) | 0.42 |
| 20261020T213620 v50 | 112 | 112.0 | 3.94 (4.45) | 5.56 | 0.59 | 70.8 % (68.5 %) [77.5 %] | 1.04 | 3.77 | 440.9 | 441.0 ± 161.1 (6) | 2.74 | 16.1 / 33.1 (600) | 4.97 vs 7.64 (-34.9 %) | 4.97 vs 5.93 (-16.1 %) | 605.7 (-27.2 %) | 0.66 |
| 20261020T224434 v51 | 93 | 93.0 | 17.34 (21.06) | 18.24 | 0.27 | 95.1 % (83.0 %) [96.5 %] | 1.16 | 14.94 | 1,613.2 | 1,861.2 ± 3,307.7 (5) | 0.56 | 17.4 / 35.8 (604) | 17.97 vs 7.71 (132.9 %) | 4.53 vs 5.97 (-24.2 %) | 682.3 (136.4 %) | 0.69 |
| 20261020T234607 v51 | 111 | 110.9 | 9.26 (10.58) | 10.86 | 4.59 | 85.3 % (74.5 %) [91.0 %] | 2.55 | 3.63 | 1,027.1 | 1,028.0 ± 1,190.0 (6) | 0.86 | 6.6 / 13.6 (617) | 6.27 vs 7.69 (-18.4 %) | 6.27 vs 5.95 (5.3 %) | 727.1 (41.3 %) | 0.71 |
| 20261021T004744 v51 | 110 | 110.0 | 10.24 (12.15) | 11.45 | 0.53 | 89.4 % (78.8 %) [93.7 %] | 1.76 | 5.80 | 1,125.9 | 1,126.0 ± 1,121.3 (6) | 1.00 | 9.6 / 19.8 (627) | 10.93 vs 7.33 (49.0 %) | 6.29 vs 5.75 (9.4 %) | 720.7 (56.2 %) | 0.76 |
| 20261021T014926 v51 | 68 | 67.9 | 5.12 (5.82) | 6.47 | 0.91 | 79.1 % (85.7 %) [82.3 %] | 1.62 | 3.16 | 347.7 | 348.0 ± 351.2 (6) | 0.99 | 16.7 / 34.7 (654) | 5.56 vs 7.34 (-24.2 %) | 5.56 vs 5.81 (-4.3 %) | 393.9 (-11.7 %) | 0.57 |
| 20261021T092850 v52 | 102 | 102.0 | 5.35 (6.07) | 6.45 | 0.40 | 83.0 % (81.9 %) [88.5 %] | 1.79 | 2.98 | 545.7 | 546.0 ± 186.3 (6) | 2.93 | 10.0 / 20.8 (663) | 6.05 vs 7.39 (-18.2 %) | 6.05 vs 5.79 (4.5 %) | 625.8 (-12.8 %) | 0.69 |
| 20261021T112438 v52 | 154 | 153.9 | 5.66 (6.40) | 6.90 | 0.92 | 82.0 % (83.2 %) [94.7 %] | 1.51 | 3.75 | 870.5 | 871.0 ± 206.6 (6) | 4.22 | 7.8 / 16.4 (669) | 5.97 vs 7.30 (-18.2 %) | 5.97 vs 5.87 (1.7 %) | 921.6 (-5.5 %) | 0.92 |
| 20261021T131746 v52 | 141 | 140.9 | 6.82 (7.85) | 8.01 | 0.87 | 85.0 % (82.5 %) [93.9 %] | 2.22 | 3.07 | 960.6 | 961.0 ± 389.2 (6) | 2.47 | 5.8 / 12.1 (677) | 7.15 vs 7.25 (-1.4 %) | 6.44 vs 5.84 (10.3 %) | 868.8 (10.6 %) | 0.91 |
| 20261021T150152 v53 | 151 | 151.0 | 5.31 (6.12) | 6.56 | 1.17 | 81.0 % (74.6 %) [92.8 %] | 1.92 | 2.77 | 801.9 | 802.0 ± 305.4 (6) | 2.63 | 6.2 / 13.0 (697) | 5.39 vs 7.47 (-27.8 %) | 4.73 vs 5.99 (-21.0 %) | 913.5 (-12.2 %) | 0.90 |
| 20261016T093835 human-demo | 50 | 300.0 | 7.58 (8.64) | 8.34 | 1.50 | 90.9 % (96.8 %) [100.0 %] | 2.30 | 3.30 | 2,274.0 | 2,274.0 ± - (1) | - | 3.4 / 6.3 (130) | 6.84 vs 7.87 (-13.1 %) | 6.84 vs 6.56 (4.2 %) | 2,145.3 (6.0 %) | 1.52 |
| 20261018T060344 v35 | 221 | 220.8 | 8.73 (10.52) | 26.50 | 12.94 | 33.0 % (39.3 %) [62.8 %] | 0.99 | 8.81 | 1,928.1 | 1,930.0 ± 3,048.9 (6) | 0.63 | 9.9 / 19.0 (321) | 13.57 vs 7.87 (72.3 %) | 5.65 vs 6.30 (-10.3 %) | 572.8 (236.6 %) | 0.68 |
| 20261018T101834 v37 | 191 | 190.8 | 5.96 (7.10) | 18.97 | 7.86 | 31.4 % (24.3 %) [48.5 %] | 1.02 | 5.84 | 1,136.9 | 1,138.0 ± 1,253.0 (6) | 0.91 | 10.9 / 21.1 (363) | 11.11 vs 7.92 (40.3 %) | 7.45 vs 6.43 (15.7 %) | 474.4 (139.7 %) | 0.65 |

(The last two rows are prt_fild06, the held-out map of v35 / v37; fill time uses this run's start
weight w0; "model" = the map model at THIS run's measured kill mix.)

### 6c. Checks: is the model right where it can be checked?

1. **Weights: exact.** In v52 run 1 every one of our 104 successful pickups moved the server's weight
   stat by exactly the table's weight x amount (`test_real_weights_match_the_servers_weight_packets`).
2. **Drop rates: right on the high-count items.** Own drops per kill, pooled over the 95 runs, against
   the model's p (sd = the binomial standard error of the measured share):

   | species (kills) | item | model p | measured | measured - model, in sd |
   |---|---|---|---|---|
   | Lunatic 1063 (3,440) | Clover 705 | 0.650 | 0.657 | +0.9 |
   | Lunatic | Apple 512 | 0.200 | 0.188 | -1.7 |
   | Lunatic | Carrot 515 | 0.110 | 0.103 | -1.3 |
   | Poring 1002 (5,502) | Jellopy 909 | 0.700 | 0.702 | +0.3 |
   | Poring | Empty Bottle 713 | 0.150 | 0.154 | +0.8 |
   | Poring | Apple 512 | 0.115 | 0.114 | -0.3 |
   | Drops 1113 (921) | Jellopy 909 | 0.750 | 0.741 | -0.7 |
   | Drops | Apple 512 | 0.190 | 0.210 | +1.5 |

   The Lunatic is not a looter, so its numbers need no carry split: they check the drop rule alone.
   The looters' numbers check the rule AND the split (section 3a): before the split, the Porings of
   v51-v53 (8 runs, 487 kills) showed 0.82 Jellopy and 0.16 Apple per kill.
3. **Value: right on the core, noisy on the tail.** Pooled over all runs, own drops per kill
   measured vs the model at the measured mixes: **V core (drops >= 1 %) -1.1 %**, V own -4.8 %,
   W +2.8 %. Per run, V core stays within about -24 % ... +17 % (v48-v53: -0.9 % pooled), while V own
   swings from -35 % to +133 %: a run either sees a tail item or it does not.
4. **One tail item decides a run's gross.** v51 run 1's 1,613 z/h includes ONE Rainbow Carrot (622,
   1,250 z, a Lunatic's 0.2 % drop): 77 % of the run's revenue. v51's pooled 1,028 z/h against v52's
   792 z/h is a Rainbow Carrot and an Unripe Apple (619, 500 z), not a better bot. Compare setups on
   K, L, V core and V / W, or pool many hours; one-hour gross z/h is mostly luck at the top.

### 6d. Findings from the measured rows

1. **Batt's demo is the benchmark: 2,274 z/h at NPC prices** (300 kills / h x 7.58 z picked per
   kill; 2,592 with Overcharge). The bot's recent hours WITHOUT a tail item earn 800-960 z/h (v52 runs
   2-3, v53):
   the gap is K (300 vs 140-154) much more than L (91 % vs 81-85 % by value).
2. **L by value is not L by count.** Batt: 90.9 % by value, 96.8 % by count -- he left a few
   valuable items; v52 run 1: 83.0 % by value, 81.9 % by count.
3. **The looters recycle what is left behind: 5,292 of the 15,918 items our kills dropped (33 %;
   31 % of the value) were CARRY** -- Porings and Drops that had picked up items and dropped them
   again when we killed them. In the early versions, which picked almost nothing, Porings carried
   whole piles (v27: 40 z of carry per kill). With v52-v53's 81-85 % completeness it is 0.8-1.2 z per
   kill (pooled per version).
4. **Capacity never binds on prt_fild08:** the GM (C 4970, w0 ~540-700) fills to 50 % in 6-33 hours
   at the bot's weight rate (Batt's rate: 3.4 h). A trip does not cost a 1-hour run anything.
5. **V / W is low and flat: 3-4 z per weight unit** (Jellopy 3 z for 1 weight). prt_fild08 is a
   kill-rate map, not a loot map.
6. **The Sharpe-like ratio of a run** is 2-4 when it sees no tail item and 0.6-1.0 when it does; the
   model's (0.5-0.9 for the bot) includes the tail risk a single hour usually does not show (section 9).

### 6e. The Crusader survival trials (costs only)

18 trials banked at the back-fill (2026-10-21 18:44-20:13), 49.0 minutes. The Crusader stands on
prt_fild08 against summoned orcsdun01 species and does not attack: **K = 0, revenue 0; the row is the
cost of staying alive.** White Potion 1,200 z (912 with Discount 10), Fly Wing 60 z (45).

| set | trials | minutes | potions / Fly Wings | cost z | cost z / h (with DC) | deaths |
|---|---|---|---|---|---|---|
| T-S6 (packs C, E: S6 tests the stop at death; no potion used) | 2 | 5.0 | 0 / 0 | 0 | 0 | 2 |
| T-S2 pack C (3 Orc Zombie + 2 Orc Skeleton) | 3 | 10.8 | 17 / 0 | 20,400 | 113,776 (86,470) | 0 |
| T-S2 pack E | 4 | 17.4 | 59 / 0 | 70,800 | 244,306 (185,673) | 0 |
| T-S2 pack F (5 OZ + 3 OS + 2 Drainliar) | 3 | 8.2 | 85 / 0 | 102,000 | 749,449 (569,581) | 0 |
| T-S3 / T-S3h (escape) | 6 | 7.7 | 0 / 6 | 360 | 2,800 (2,100) | 0 |
| **all** | 18 | 49.0 | 161 / 6 | 193,560 | 236,945 | 2 |

**The economic reading:** the model's best Crusader map earns ~12,000-23,000 z/h (section 7). Even pack
C's burn rate (114k z/h of White Potions, while not attacking) is 5-9x that. Farming pays only if the
potion use per hour falls by an order of magnitude: killing what attacks (the trials do not), fewer
attackers at once, Increase HP Recovery + natural regen (~1,250 HP/min standing, crusader-build.md
3f, but only below 50 % weight), and Red Potions (2.89 HP per zeny against the White's 0.80,
crusader-build.md 4b) where weight allows. The trials measured 2,000-4,500 HP of damage per minute
from pack C (survive_judge); 12,000 z/h buys ~160 HP/min of White Potions or ~580 HP/min of Red.

---

## 7. The map model: prt_fild08, orcsdun01 and six Base-60 Crusader candidates

`econ_model.py table --L 0.9` (+ `--C 255`, `--oc`). The Crusader MAIN on every map: K = the ROUGH
K_est (section 5), L = 0.90 (assumed: Batt's demo 0.91 by value), C = 1,155 (50 % of 4,150 minus 920
of gear; the trials measured the Crusader carrying 1,340-1,820 at the start, which leaves 255-735:
the second fill column uses 255), costs 0 (unknown: see 6e), gear 310,000 z. T = the faster of the
sell trip and the Kafra trip (its storage fee per trip).

| map | species | HP mean | Undead / Demon | aggressive | V z/kill (core + tail) | rare_v | W / kill | V / W | V / HP | K_est / h | T sell / Kafra s (fee) | fill h C 1155 / 255 | u (C 1155) | G z/h (OC) | N z/h incl. trips | payback h | N / gear per h | Sharpe-like |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| prt_fild08 | 4 | 107 | 0 % | 0 % | 7.4 (6.0 + 1.4) | 0.0 | 1.59 | 4.7 | 0.070 | 346 | 97 / 84 (40) | 2.3 / 0.5 | 0.990 | 2,319 (2,684) | 2,279 | 136.0 | 0.73 % | 1.46 |
| prt_fild06 | 6 | 95 | 0 % | 0 % | 9.1 (7.6 + 1.4) | 0.0 | 1.64 | 5.5 | 0.096 | 329 | 121 / 102 (40) | 2.4 / 0.5 | 0.988 | 2,685 (3,176) | 2,637 | 117.6 | 0.85 % | 1.63 |
| orcsdun01 | 7 | 1199 | 67 % | 82 % | 56.0 (54.2 + 1.8) | 1.3 | 1.21 | 46.1 | 0.047 | 242 | 534 / 81 (130) | 4.4 / 1.0 | 0.995 | 12,214 (15,078) | 12,121 | 25.6 | 3.91 % | 3.75 |
| gef_fild10 | 6 | 1494 | 0 % | 80 % | 126.9 (125.6 + 1.3) | 4.0 | 1.15 | 110.1 | 0.085 | 204 | 479 / 90 (130) | 5.5 / 1.2 | 0.995 | 23,297 (28,838) | 23,166 | 13.4 | 7.47 % | 3.20 |
| orcsdun02 | 7 | 2028 | 32 % | 48 % | 83.5 (78.7 + 4.7) | 5.5 | 1.36 | 61.2 | 0.041 | 172 | 581 / 155 (130) | 5.5 / 1.2 | 0.992 | 12,939 (15,967) | 12,814 | 24.2 | 4.13 % | 3.18 |
| pay_dun01 | 6 | 1909 | 68 % | 73 % | 92.3 (61.3 + 31.0) | 0.1 | 1.88 | 49.0 | 0.048 | 200 | 247 / 234 (90) | 3.4 / 0.8 | 0.981 | 16,642 (20,564) | 16,304 | 19.0 | 5.26 % | 0.97 |
| pay_dun02 | 11 | 2020 | 61 % | 81 % | 78.7 (69.6 + 9.2) | 0.4 | 1.80 | 43.8 | 0.039 | 202 | 557 / 544 (90) | 3.5 / 0.8 | 0.959 | 14,308 (17,679) | 13,698 | 22.6 | 4.42 % | 1.60 |
| moc_pryd02 | 6 | 2827 | 70 % | 85 % | 108.7 (87.8 + 20.9) | 3.1 | 1.72 | 63.1 | 0.038 | 181 | 187 / 181 (90) | 4.1 / 0.9 | 0.988 | 17,688 (21,882) | 17,454 | 17.8 | 5.63 % | 1.22 |
| ama_dun01 | 3 | 5431 | 98 % | 42 % | 308.6 (308.6 + 0.0) | 3.5 | 3.21 | 96.0 | 0.057 | 82 | 408 / 401 (50) | 4.9 / 1.1 | 0.978 | 22,827 (28,272) | 22,306 | 13.9 | 7.20 % | 1.56 |

**Why each candidate** (`econ_model.CANDIDATES`; picked from `econ_model.py screen`, every map with
>= 20 normal spawns, for monster levels a Base-60 Crusader hits and survives, Undead / Demon share
for Demon Bane and Divine Protection, and income):

| map | why |
|---|---|
| gef_fild10 | the orc field the Crusader walks through to orcsdun01 (in_orcs01): Orc Lady / Orc Warrior lv 24-31, NOT undead (no Demon Bane) -- the baseline beside orcsdun01 |
| orcsdun02 | Orc Dungeon F2, the stairs from orcsdun01: Orc Skeleton (Undead, lv 28) + Zenorc (lv 31, FLEE 108: MAIN hits 55 %); 5 Orc Archers lv 49 |
| pay_dun01 | Payon Cave F2: Soldier / Archer Skeleton (Undead lv 29-31: Demon Bane + Divine Protection, MAIN hits 100 %); 68 % Undead / Demon |
| pay_dun02 | Payon Cave F3: Munak / Bongun / Skeletons (Undead lv 29-32) with Hydras and plants |
| moc_pryd02 | Pyramid F2: Mummy (lv 37, 5,176 HP) + the Skeletons (Undead) with 5 Isis (Demon lv 47); 70 % Undead / Demon |
| ama_dun01 | Amatsu Dungeon F1: Miyabi Doll (Demon lv 33) + Firelock Soldier (Undead lv 47): 98 % Undead / Demon and the highest V per kill of the Undead maps; the top end for Base 60 (MAIN hits ~80 %; 2 Shinobi lv 69) |

**Reading the table:**

1. **The trip barely matters at these weights:** u = 0.96-0.995. On the Crusader maps the bag
   fills to 50 % in 3.4-5.5 hours of farming at C 1,155 (0.8-1.2 h at C 255). From orcsdun01 the
   nearest NPC that buys (geffen_in) is a 9-minute round trip, but the gef_fild10 Kafra (130 z) is
   81 s: storage resets the bag sooner.
2. **The ranking by income (G):** gef_fild10 ~23,300 z/h and ama_dun01 ~22,800 lead; moc_pryd02,
   pay_dun01, pay_dun02 ~14,300-17,700; orcsdun01 and orcsdun02 ~12,200-12,900 -- each at its own
   rough K_est. orcsdun01's V per kill (56 z) is its main species', the Orc Zombie (80 of 135 spawns,
   ~57 z per kill); gef_fild10's Orc Lady (70 of 119, ~181 z per kill) carries that map.
3. **Payback (the P/E analogue) of the 310,000 z of gear:** 13-14 hours on gef_fild10 / ama_dun01,
   18-23 on the Undead caves and the Pyramid, 24-26 on the Orc Dungeon -- before potions.
4. **Risk:** pay_dun01 (V_tail 31 of 92 z) and moc_pryd02 have Sharpe-like ratios near 1: a third
   of their income is 0.1-1 % drops. orcsdun01 / orcsdun02 / gef_fild10 earn from common drops
   (Sharpe ~3-4).
5. **Costs are the unknown that decides it** (6e): none of these rows includes potions. A map whose
   monsters hit a Base-60 Crusader less (FLEE 122 against their HIT; Divine Protection -54 against
   Undead / Demon) will burn fewer potions; the trials say the burn rate, not the drop table, is
   the first-order term.
6. **K-free comparisons** (no K_est needed): V per kill, V / W, V per HP (zeny per point of monster
   HP: what a fixed DPS converts into zeny). By V per HP, gef_fild10 (0.085) beats orcsdun01 (0.047)
   and every Undead map (0.038-0.057).

## 8. Model vs measured

| where | measured | model | error |
|---|---|---|---|
| prt_fild08, 95 runs pooled, V core (drops >= 1 %) per kill | own drops | at each run's kill mix | **-1.1 %** |
| same, V own drops per kill (with the tail) | | | -4.8 % |
| same, W own drops per kill | | | +2.8 % |
| v48-v53 pooled (21 runs): V core / V own / W | | | -0.9 % / -10.6 % / +1.6 % |
| one run (v48-v53): V core | | | -24 % ... +17 % |
| one run (v48-v53): W own (a Knife weighs 40: one is +0.3 per kill) | | | -22 % ... +54 % |
| one run (v48-v53): V own | | | -35 % ... +133 % (a tail item or not) |
| one run: gross z/h (model at the run's K and L) | | | -27 % ... +136 % |
| Batt's demo: V core / V own / gross | | | +4.2 % / -13.1 % / +6.0 % |
| prt_fild06 (v35, v37): V core | | | -10.3 % / +15.7 % |
| orcsdun01 | **no kill measured yet** (Batt's orcsdun01 demo got no input; the trials do not attack) | | - |
| the trips (T), K_est, the Crusader's costs | not measured | | - |

The error column is in every run's economics block (run_row's second table: "MODEL ... (err)").


---

## 9. Limits (what the packets cannot see) and UNVERIFIED

- **No price was ever observed on the live server.** No banked session holds a shop packet (searched
  every session in `/dev/shm/poring-lab-demo`; the disk archive holds older NPC / cursor sessions
  only). The prices are the pinned source's rules. A one-minute live check would prove them: open
  one Tool Dealer with the GM and read `shop_buy_list` (price and discount price per item) and
  `shop_sell_list` (price and overcharge per inventory item) -- the decoders exist.
- **The weights ARE verified on the server:** in v52 run 1 every one of our 104 successful pickups
  moved the server's weight stat by exactly the table's weight x amount (a test).
- **The drop rates are verified** on the high-count items of the four prt_fild08 species (section
  6c; the Lunatic, a non-looter, checks the rule alone), not on the tail or the rares, and not on
  any other map: orcsdun01 and the candidates rest on the same rule and the same code path, unchecked.
- **Mark-to-market, never realised:** the hunt runs never sell; the runner drops its inventory at
  the end of each run (stacked falls after the window, never attributed to a kill). V is what the
  picked items WOULD fetch.
- **The kill attribution** is `arm_judge`'s (a death <= 1.5 s after our damaging hit); a kill by
  something else, or a death later than 1.5 s, is not ours. Drops are attributed by time and place
  (`drops_of_kill`); checked in v52 run 1 and Batt's demo: no floor item fell into two kills'
  windows, and every fall in the window belonged to a kill of ours but one.
- **Carry is a lower bound** (section 3a). The model has no looter economy: on prt_fild08 the
  monsters recycle what the bot leaves behind.
- **Pet eggs** go to the inventory, not the floor: invisible to the drop measurement (rares anyway).
- **Costs the packets cannot see:** a skill's SP, the experience a death costs (an EXP penalty, not
  zeny), Kafra and teleport fees (not used in the banked runs).
- **The prt_fild08 runs cost nothing** because the Novice GM is immune (`@monsterignore`) and uses
  no items; their net = gross. The Crusader trials are the opposite: summoned packs, no kills.
- **The trip** is a walking model (section 4) with assumed NPC (20 s) and map-change (2 s) times;
  Wings, Kafra teleports and the Peco are not modelled.
- **K_est is rough** (section 5). Every map row that uses it says so.
- **The Sharpe-like ratio** of a 1-hour run has 6 windows; the sample ratio misses the tail (an
  Unripe Apple, 500 z at 0.2 %, is in the model's variance whether or not a run saw one), so a
  run's measured ratio is usually ABOVE the model's.

---

## 10. The dashboard (`/economy`, Batt 2026-11-11)

Batt: "make a dashboard page of business results (P&L), because I will teach economics too". The
console's **Economy** page (`http://<host>:3000/economy`) shows banked runs at the fixed NPC prices of
section 2. It reads exports, so a run appears there only after someone exports it:

```
    econ_dash.py export SESSION_DIR [SESSION_DIR ...] --name NAME   # -> data/econ/dashboard/NAME.json
    econ_dash.py list                                               # the exports there
```

- SESSION_DIR is a session directory (`events.jsonl`, `packets.jsonl.gz`, `manifest.json`), e.g. an
  archived run under the NAS's `scratch-archive/<date>/demo-sessions/`; a plain session id works too
  (`/dev/shm`, else the NAS). NAME: letters, digits, `_ . -`, at most 64 characters.
- A worktree has no `data/`: add `--data /home/bot/docker/poring-lab/data` (the item table, the KB
  names, and the default output directory all live under it).
- The backend serves the exports read-only: `GET /economy/list` and `GET /economy/data/NAME`
  (`routes_economy.py`; the public listener only, as `/hardware`).

**What an export holds** (one JSON, per run and pooled): the run's facts (session, map, character,
judged window and hours, kills, deaths) and COUNTS, never only rates, so the page can recompute every
rate with edited prices:

| Table | Counted by | Columns on the page |
|---|---|---|
| Income | `dungeon_judge.item_gains`: every inventory gain by cause. picked = <= 2 s after our pickup request; **stolen = Steal** (<= 1.5 s after a Steal's SP fall) **+ Snatcher** (<= 1 s after our own attack act, dungeon@8). "Other" and "staged" gains are listed in the export and are NOT income | picked, stolen, total, per hour, NPC sell (editable), Overcharge, zeny / h plain and Overcharge |
| Kills | `econ_row.kill_species` (section 3's kill rule) | species, kills, per hour |
| Drops | the kill rows section 3 measures (`dungeon_judge.kills_loot`) | dropped by our kills, per hour, picked share |
| Consumables | `econ_row.uses` (our successful item uses) | used, per hour, NPC buy (editable), Discount, cost / h plain and Discount |

**The P&L per hour** (the page's six tiles), h = the judged hours:

- gross plain = sum over items of (picked + stolen) x NPC sell / h; gross Overcharge the same at the
  Overcharge price;
- cost plain = sum over consumables of used x NPC buy / h; cost Discount the same at the Discount price;
- **net plain = gross plain - cost plain; net best = gross Overcharge - cost Discount.**

An edited sell price gives its Overcharge price by section 2's rule (per unit, x 1.24, truncated);
an edited buy price its Discount price (x 0.76, truncated, at least 1). Unedited, the Discount price
is the table's: the cheapest shop that gives the discount. `src/lib/econ.ts` repeats the rule and its
tests pin it to the Python function's outputs. **Edited prices stay in the viewer's browser**
(localStorage), with a reset per row and for all, and are never sent to the server.

**Why the gross here is larger than section 3's `G`:** `G` counts the PICKED drops of our kills
only. The dashboard counts every income gain, and on the Rogue most of it is Snatcher's. In the
xmas_dun02 pilots p57 and p58 (2026-11-11) section 3's gross is 12,693 and 11,597 z/h; the dashboard's
33,928 and 58,223 z/h (18 of p57's 29 gains, 37 of p58's 57 were Snatcher's).

**Checks.** Every export cross-checks its own totals against `dungeon_judge.items_value` (the gross,
plain and Overcharge), `econ_row.measure` (the costs) and the value of our kills' picked drops; on
a mismatch nothing is written. The p57 + p58 export was also checked by hand against the RAW
packets (`tests/test_econ_dash.py`):

| | p57 | p58 |
|---|---|---|
| judged window (run_start..run_end) | 25.002 min | 25.035 min |
| kills (a died vanish <= 1.5 s after our damaging act) / per h | 35 / 84.0 | 65 / 155.8 |
| income gains: picked + stolen (all Snatcher; Steal was off) | 11 + 18 = 29 | 20 + 37 = 57 |
| our item uses in the window | 0 (a Fly Wing 0.37 s after run_end is outside) | 0 |
| gross plain / Overcharge, z | 14,138 / 17,523 | 24,294 / 30,111 |
| per hour: gross plain / best = net plain / best (no cost) | 33,928 / 42,052 | 58,223 / 72,164 |

The prices came from the db by hand (Sell, else Buy / 2; x 1.24 truncated) for all ten items and
matched the table. A survival trial with 26 potions checks the consumable path (its uses per item id
equal survive_judge's count; its cost equals econ_row's).

**Limits:** everything in section 9, plus: the values are mark-to-market (nothing is sold); items
used later (a healing item that was income) are not netted; names come from the run-time KB in the
server's language, while the page's own text is English.
