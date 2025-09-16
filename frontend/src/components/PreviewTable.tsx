import type { Transaction as Tx } from "../lib/csv";

export default function PreviewTable({ rows }: { rows: Tx[] }) {
  if (rows.length === 0) return <em>No rows yet</em>;
  return (
    <table style={{ width: "100%", borderCollapse: "collapse" }}>
      <thead>
        <tr>
          <th align="left">date</th>
          <th align="left">description</th>
          <th align="right">amount</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={`${r.date}-${r.description}-${r.amount}-${i}`}>
            <td>{r.date}</td>
            <td>{r.description}</td>
            <td align="right">{r.amount}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
