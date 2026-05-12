import fs from "fs";
import path from "path";
import { getDb } from "./db";

const CONFIG_PATH = path.join(
  process.cwd(),
  "..",
  "config",
  "betting_config.json"
);
const COUPONS_DIR = path.join(process.cwd(), "..", "betting", "coupons");

export function getBankroll(): number {
  try {
    const raw = fs.readFileSync(CONFIG_PATH, "utf-8");
    const config = JSON.parse(raw);
    return config.current_bankroll ?? 0;
  } catch {
    return 0;
  }
}

export function getEventsScanned(date: string): number {
  try {
    const db = getDb();
    const row = db
      .prepare(
        "SELECT COUNT(*) as count FROM events WHERE event_date = ? OR date(created_at) = ?"
      )
      .get(date, date) as { count: number } | undefined;
    return row?.count ?? 0;
  } catch {
    return 0;
  }
}

export function getActiveCoupons(): number {
  try {
    const files = fs.readdirSync(COUPONS_DIR);
    return files.filter((f) => f.endsWith(".md")).length;
  } catch {
    return 0;
  }
}

export function getLatestCoupon(): { filename: string; content: string } | null {
  try {
    const files = fs
      .readdirSync(COUPONS_DIR)
      .filter((f) => f.endsWith(".md"))
      .sort()
      .reverse();
    if (files.length === 0) return null;
    const filename = files[0];
    const content = fs.readFileSync(path.join(COUPONS_DIR, filename), "utf-8");
    return { filename, content };
  } catch {
    return null;
  }
}

export function getCouponList(): { filename: string; date: string }[] {
  try {
    const files = fs
      .readdirSync(COUPONS_DIR)
      .filter((f) => f.endsWith(".md"))
      .sort()
      .reverse();
    return files.map((f) => ({
      filename: f,
      date: f.replace(".md", ""),
    }));
  } catch {
    return [];
  }
}

export function getCouponContent(filename: string): string | null {
  try {
    const safeName = path.basename(filename);
    const filePath = path.join(COUPONS_DIR, safeName);
    return fs.readFileSync(filePath, "utf-8");
  } catch {
    return null;
  }
}

export function getPipelineStatus(): string {
  return "Idle";
}
