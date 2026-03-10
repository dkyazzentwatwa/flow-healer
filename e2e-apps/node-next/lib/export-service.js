const TODO_EXPORT_COLUMNS = ["id", "title", "completed"];

export function escapeCsvValue(value) {
  const normalized = String(value ?? "");

  if (!/[",\n\r]/.test(normalized)) {
    return normalized;
  }

  return `"${normalized.replaceAll("\"", "\"\"")}"`;
}

export function toCsvRows(items, columns) {
  const header = columns.join(",");
  const rows = items.map((item) =>
    columns.map((column) => escapeCsvValue(item?.[column])).join(","),
  );

  return [header, ...rows];
}

export function toTodoCsv(todos) {
  return toCsvRows(todos, TODO_EXPORT_COLUMNS).join("\n");
}
