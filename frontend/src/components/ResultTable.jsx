function formatCellValue(cellValue) {
  if (cellValue === null || cellValue === undefined) return "—";
  if (typeof cellValue === "number") {
    return cellValue.toLocaleString(undefined, { maximumFractionDigits: 2 });
  }
  return String(cellValue);
}

export default function ResultTable({ columns, rows }) {
  if (!columns?.length || !rows?.length) return <p className="muted">No rows returned.</p>;
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            {columns.map((columnName) => (
              <th key={columnName}>{columnName}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, rowIndex) => (
            <tr key={rowIndex}>
              {row.map((cellValue, columnIndex) => (
                <td key={columnIndex} className={typeof cellValue === "number" ? "num" : ""}>
                  {formatCellValue(cellValue)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
