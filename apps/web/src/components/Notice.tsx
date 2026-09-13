export function Notice({
  text,
  tone = "info",
}: {
  text: string;
  tone?: "info" | "success" | "error";
}) {
  return (
    <div className={`notice ${tone}`}>
      <span>{tone === "success" ? "✓" : tone === "error" ? "!" : "·"}</span>
      <p>{text}</p>
    </div>
  );
}
