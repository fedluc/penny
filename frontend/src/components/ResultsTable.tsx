import type { Classified } from "../lib/api";

export default function ResultsTable({ rows }: { rows: Classified[] }) {
  return (
    <table style={{ width: "100%", borderCollapse: "collapse" }}>
      <thead>
        <tr>
          <th align="left">date</th>
          <th align="left">description</th>
          <th align="right">amount</th>
          <th align="left">category</th>
          <th align="right">confidence</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={`${r.date}-${r.description}-${r.amount}-res-${i}`}>
            <td>{r.date}</td>
            <td>{r.description}</td>
            <td align="right">{r.amount}</td>
            <td>{r.category}</td>
            <td align="right">{r.confidence != null ? r.confidence.toFixed(2) : "—"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
