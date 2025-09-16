import { useEffect, useMemo, useRef, useState } from "react";
import BrandLink from "../components/BrandLink";
import { fetchTransactions, type ServerClassified } from "../lib/api";
import "./VisualizeExpenses.css";

const PAGE_SIZE = 50;

export default function VisualizeExpenses() {
  const [rows, setRows] = useState<ServerClassified[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);
  const [hasMore, setHasMore] = useState(true);

  const abortRef = useRef<AbortController | null>(null);

  async function loadPage(nextOffset: number) {
    setLoading(true);
    setError(null);
    try {
      // Abort a previous in-flight call if any
      abortRef.current?.abort();
      abortRef.current = new AbortController();

      const chunk = await fetchTransactions(PAGE_SIZE, nextOffset);
      setRows(prev => nextOffset === 0 ? chunk : [...prev, ...chunk]);
      setHasMore(chunk.length === PAGE_SIZE);
      setOffset(nextOffset + chunk.length);
    } catch (e: any) {
      if (e?.name === "AbortError") return;
      setError(e?.message ?? String(e));
    } finally {
      setLoading(false);
    }
  }

  // initial load
  useEffect(() => {
    loadPage(0);
    return () => abortRef.current?.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const formatted = useMemo(
    () =>
      rows.map((r) => ({
        date: r.date ?? "",
        description: r.description ?? "",
        amount: r.amount ?? 0,
        category_id: r.category_id ?? null,
        hash: r.hash ?? "",
        created_at: r.created_at ?? "",
      })),
    [rows]
  );

  return (
    <>
      <BrandLink />
      <main className="page visualize">
        <div className="container">
          <h1 className="section-title" style={{ fontSize: 24 }}>Transactions</h1>
          <p className="muted">Fetched from <code>/transactions</code> ({rows.length}{hasMore ? "+" : ""} rows)</p>

          <section className="section">
            <div className="card" style={{ overflowX: "auto" }}>
              <table>
                <thead>
                  <tr>
                    <th style={{ whiteSpace: "nowrap" }}>Date</th>
                    <th>Description</th>
                    <th style={{ textAlign: "right", whiteSpace: "nowrap" }}>Amount</th>
                    <th style={{ whiteSpace: "nowrap" }}>Category&nbsp;ID</th>
                    <th>Hash</th>
                    <th style={{ whiteSpace: "nowrap" }}>Created&nbsp;At</th>
                  </tr>
                </thead>
                <tbody>
                  {formatted.length === 0 && !loading && !error && (
                    <tr><td colSpan={6} className="muted">No data</td></tr>
                  )}
                  {formatted.map((r, i) => (
                    <tr key={`${r.hash || "row"}-${i}`}>
                      <td>{r.date}</td>
                      <td>{r.description}</td>
                      <td style={{ textAlign: "right" }}>
                        {typeof r.amount === "number" ? r.amount.toFixed(2) : ""}
                      </td>
                      <td>{r.category_id ?? ""}</td>
                      <td style={{ maxWidth: 220, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {r.hash}
                      </td>
                      <td>{r.created_at}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="section row wrap">
            <button
              className="btn btn-outline"
              onClick={() => loadPage(0)}
              disabled={loading}
              title="Reload from start"
            >
              Refresh
            </button>
            <button
              className="btn btn-primary"
              onClick={() => loadPage(offset)}
              disabled={loading || !hasMore}
              title="Fetch next page"
            >
              {loading ? "Loading…" : hasMore ? "Load more" : "No more results"}
            </button>
            {error && <p className="muted" style={{ color: "salmon" }}>{error}</p>}
          </section>
        </div>
      </main>
    </>
  );
}
