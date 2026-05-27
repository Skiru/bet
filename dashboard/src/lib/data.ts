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
        "SELECT COUNT(DISTINCT event_key) as count FROM scan_results WHERE betting_date = ?"
      )
      .get(date) as { count: number } | undefined;
    return row?.count ?? 0;
  } catch {
    return 0;
  }
}

export function getActiveCoupons(): number {
  try {
    // First try DB coupons table
    const db = getDb();
    const row = db
      .prepare(
        "SELECT COUNT(*) as count FROM coupons WHERE status = 'pending' OR status = 'active'"
      )
      .get() as { count: number } | undefined;
    if (row && row.count > 0) return row.count;
    // Fallback to file count
    const files = fs.readdirSync(COUPONS_DIR);
    return files.filter((f) => f.endsWith(".md")).length;
  } catch {
    try {
      const files = fs.readdirSync(COUPONS_DIR);
      return files.filter((f) => f.endsWith(".md")).length;
    } catch {
      return 0;
    }
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
  try {
    const db = getDb();
    const today = new Date().toISOString().slice(0, 10);
    // Check if pipeline ran today by looking at scan_results
    const row = db
      .prepare(
        "SELECT COUNT(*) as count FROM scan_results WHERE betting_date = ?"
      )
      .get(today) as { count: number } | undefined;
    if (row && row.count > 0) return "Complete";
    return "Idle";
  } catch {
    return "Idle";
  }
}

export function getLMStudioConfig(): {
  enabled: boolean;
  model: string;
  baseUrl: string;
} {
  try {
    const configPath = path.join(
      process.cwd(),
      "..",
      "config",
      "lmstudio_config.json"
    );
    const raw = fs.readFileSync(configPath, "utf-8");
    const config = JSON.parse(raw);
    return {
      enabled: true,
      model: config.model ?? "qwen/qwen3.6-27b",
      baseUrl: config.base_url ?? "http://localhost:1234/v1",
    };
  } catch {
    return { enabled: false, model: "N/A", baseUrl: "N/A" };
  }
}

export function getSportBreakdown(
  date: string
): { sport: string; count: number }[] {
  try {
    const db = getDb();
    const rows = db
      .prepare(
        "SELECT sport, COUNT(DISTINCT event_key) as count FROM scan_results WHERE betting_date = ? GROUP BY sport ORDER BY count DESC"
      )
      .all(date) as { sport: string; count: number }[];
    return rows;
  } catch {
    return [];
  }
}
