import { Icon } from "./Icon";

export function Notice({
  text,
  tone = "info",
}: {
  text: string;
  tone?: "info" | "success" | "error" | "warning";
}) {
  return (
    <div className={`notice ${tone}`}>
      <span><Icon name={tone === "success" ? "check" : tone === "info" ? "info" : "alert"} size={15} /></span>
      <p>{text}</p>
    </div>
  );
}
