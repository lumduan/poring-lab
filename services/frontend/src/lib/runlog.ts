/** The Run log (Batt 2026-11-21): "What she does" kept as history, set on the Settings page.
 * The backend's routes_runlog.py is the only writer of settings/run-log.json; the Run helper reads
 * it at every Run's start (poring_env.runlog has the format; the checks here mirror its own). */

export type RunLogView = {
  store: "ok" | "default" | "unreadable";
  problem: string | null;
  revision: number;
  record: boolean;
  folder: string;
  max_total_mb: number;
  default: { record: boolean; folder: string; max_total_mb: number };
  max_folder: number;
  max_total_mb_range: [number, number];
  files: string[];
  saved?: boolean;
};

const REASONS: Record<string, string> = {
  folder_empty: "Give a folder.",
  folder_too_long: "The folder's path is too long.",
  folder_bad_character: "The folder's path has a character a path cannot hold.",
  folder_dotdot: "A folder path may not go up with “..”: give the whole path instead (e.g. /mnt/nas/bot-logs).",
  folder_root: "Not the root of the disk: give a folder.",
  max_not_a_whole_number: "The size must be a whole number of MB.",
  max_out_of_range: "The size is out of range.",
  revision_conflict: "Someone saved this in the meantime: the page shows it again; try once more.",
  settings_store_missing: "The settings store is not mounted on the backend.",
  read_back_failed: "The file was written but did not read back the same: not saved.",
  csrf_invalid: "The page's token is old: reload the page.",
};

export function runLogReasonText(reason: string): string {
  return REASONS[reason] ?? `Refused (${reason}).`;
}

/** The checks the backend makes too (poring_env.runlog.folder_problem / max_problem). */
export function folderProblem(folder: string, maxLen: number): string | null {
  const f = folder.trim();
  if (!f) return "folder_empty";
  if (f.length > maxLen) return "folder_too_long";
  if (/[\0\n\r]/.test(f)) return "folder_bad_character";
  const parts = f.replace(/\\/g, "/").split("/").filter(Boolean);
  if (parts.includes("..")) return "folder_dotdot";
  if (parts.length === 0) return "folder_root";
  return null;
}

export function maxProblem(mb: number, range: [number, number]): string | null {
  if (!Number.isInteger(mb)) return "max_not_a_whole_number";
  if (mb < range[0] || mb > range[1]) return "max_out_of_range";
  return null;
}

/** Where a Run's log lands, as the helper names it (poring_env.runlog.run_dir_name). */
export function exampleRunFolder(folder: string, now: Date = new Date()): string {
  const p = (n: number) => String(n).padStart(2, "0");
  const stamp = `${now.getFullYear()}${p(now.getMonth() + 1)}${p(now.getDate())}-${p(now.getHours())}${p(now.getMinutes())}${p(now.getSeconds())}`;
  return `${folder.replace(/\/+$/, "")}/${stamp}-<run>/`;
}
