import Papa from "papaparse";

export type Transaction = {
  date: string;
  description: string;
  amount: number;
};

export type ParseStats = { total: number; kept: number };

/** Robust amount parser: SEK/kr/symbols, spaces, comma decimal, etc. */
export function normalizeAmount(v: unknown): number | null {
  if (typeof v === "number" && !Number.isNaN(v)) return v;
  let s = String(v ?? "").trim();
  if (!s) return null;
  // strip common currency labels/symbols
  s = s.replace(/(sek|kr|\$|€|£)/gi, "");
  // strip normal & non-breaking spaces
  s = s.replace(/[\s\u00A0\u202F]/g, "");
  const hasComma = s.includes(",");
  const hasDot = s.includes(".");
  // Adjust number format if needed
  if (hasComma && !hasDot) {
    // "1.234,56" or "1234,56" → "1234.56"
    s = s.replace(/\./g, "");
    s = s.replace(",", ".");
  } else {
    // "1,234.56" or "1234" → "1234.56" / "1234"
    s = s.replace(/,/g, "");
  }
  // also handle parentheses negatives: (123.45) → -123.45
  const neg = /^\(.*\)$/.test(s);
  if (neg) s = s.slice(1, -1);
  const n = Number(s);
  if (Number.isNaN(n)) return null;
  return neg ? -n : n;
}

/** Parse CSV text into normalized transactions + stats. */
export function parseCsv(text: string): { rows: Transaction[]; stats: ParseStats } {
  const parsed = Papa.parse(text, {
    header: true,
    skipEmptyLines: true,
    transformHeader: (h) => h.toLowerCase().trim(),
  });
  const raw = (parsed.data as any[]) ?? [];
  const rows = raw.map((r) => {
    const date =
      r.date || r["transaction date"] || r["booking date"] || r.timestamp || r.datum;
    const description =
      r.description || r.memo || r.text || r.payee || r.merchant || r.narrative || r.beskrivning;
    const amountRaw =
      r.amount ?? r["amount (sek)"] ?? r.debit ?? r.credit ?? r.belopp ?? r["belopp (sek)"];
    const amount = normalizeAmount(amountRaw);
    return {
      date: date ? String(date).trim() : "",
      description: String(description || "").trim(),
      amount,
    };
  });
  const cleaned = rows.filter(
    (t) => t.description && typeof t.amount === "number" && !Number.isNaN(t.amount)
  ) as Transaction[];
  return { rows: cleaned, stats: { total: raw.length, kept: cleaned.length } };
}
