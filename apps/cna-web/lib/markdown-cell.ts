// Text for one cell of a Markdown table, safe to put between two `|` delimiters.
//
// Order matters: collapse white space and cut to length first, then escape. Escaping first and cutting
// afterwards can leave a lone trailing backslash, which would escape the pipe that closes the cell.
// Backslashes are escaped before pipes so that a value ending in "\" cannot swallow the "\" that escapes
// the next pipe (CodeQL js/incomplete-sanitization).
export function markdownCell(value: string | null | undefined, max: number): string {
  const text = (value ?? "—").replace(/\s+/g, " ").slice(0, max);
  return text.replace(/\\/g, "\\\\").replace(/\|/g, "\\|");
}
