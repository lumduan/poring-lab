// The HUD SCENE (Batt 2026-10-08, H.264-style): a RETAINED overlay drawn on EVERY frame until told
// otherwise. Keyframes (hud_scene) carry the full state, deltas (hud_delta) add / move / remove, and
// one global motion per frame (hud_motion) shifts every world-anchored object; screen-anchored
// objects never shift. Pure, unit tested with `node --test` (src/lib/scene.test.ts). Display only:
// every label is drawn as TEXT (canvas fillText), never markup.

import type { HudDelta, HudMotion, HudScene, SceneObject } from "./protocol.ts";

export const MOTION_RING = 240; // ~10-20 s of moving frames
export type Offset = { x: number; y: number };
export type SceneBox = { x: number; y: number; w: number; h: number; kind: string; cls: string; label: string };

type Motion = { fid: number; t: number; offset: Offset };

export class SceneStore {
  objects = new Map<number, SceneObject>();
  seq = -1;
  stale = true; // no keyframe yet, or a delta was missed: wait for the next keyframe
  motions: Motion[] = [];
  received = 0;

  keyframe(m: HudScene): void {
    this.objects = new Map(m.objects.map((o) => [o.id, o]));
    this.seq = m.seq;
    this.stale = false;
    this.received += 1;
    this.pushMotion(m.frame_id, m.t_mono_ns, m.offset);
  }

  delta(m: HudDelta): void {
    this.received += 1;
    if (this.stale || m.seq !== this.seq + 1) {
      this.stale = true; // a gap: the next keyframe repairs it
      return;
    }
    this.seq = m.seq;
    for (const o of m.add) this.objects.set(o.id, o);
    for (const mv of m.move) {
      const o = this.objects.get(mv.id);
      if (o) this.objects.set(mv.id, { ...o, box: mv.box, conf: mv.conf ?? o.conf });
    }
    for (const id of m.remove) this.objects.delete(id);
  }

  motion(m: HudMotion): void {
    this.received += 1;
    this.pushMotion(m.frame_id, m.t_mono_ns, m.offset);
  }

  private pushMotion(fid: number, t: number, offset: Offset): void {
    this.motions.push({ fid, t, offset });
    this.motions.sort((a, b) => a.t - b.t);
    if (this.motions.length > MOTION_RING) this.motions.splice(0, this.motions.length - MOTION_RING);
  }

  /** The motion offset of the displayed frame: exact by its bus frame_id, else the latest one at
   * or before its capture time (the scene was still since), else none yet. */
  offsetFor(frameId: number | null, frameNs: number | null): Offset | null {
    if (frameId != null && frameId >= 0) {
      for (let i = this.motions.length - 1; i >= 0; i--) if (this.motions[i].fid === frameId) return this.motions[i].offset;
    }
    if (frameNs == null) return this.motions.length ? this.motions[this.motions.length - 1].offset : null;
    let best: Motion | null = null;
    for (const m of this.motions) if (m.t <= frameNs) best = m;
    return best ? best.offset : this.motions.length ? this.motions[0].offset : null;
  }

  /** Every object in canvas pixels for the displayed frame. */
  boxes(frameId: number | null, frameNs: number | null, width: number, height: number): SceneBox[] {
    if (this.stale) return [];
    const off = this.offsetFor(frameId, frameNs) ?? { x: 0, y: 0 };
    const out: SceneBox[] = [];
    for (const o of this.objects.values()) {
      const dx = o.anchor === "world" ? off.x : 0;
      const dy = o.anchor === "world" ? off.y : 0;
      const conf = o.conf == null ? "" : ` ${Math.round(o.conf * 100)}%`;
      out.push({
        x: (o.box.x + dx) * width,
        y: (o.box.y + dy) * height,
        w: o.box.w * width,
        h: o.box.h * height,
        kind: o.kind,
        cls: o.cls,
        label: o.kind === "unit" || o.kind === "sign" ? `${o.cls}${conf}` : "",
      });
    }
    return out;
  }
}
