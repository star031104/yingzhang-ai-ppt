import { useToasts } from "../store/toasts";
import { Icon } from "./Icon";

export function Toaster() {
  const { toasts, dismiss } = useToasts();
  return (
    <div className="toaster" role="status" aria-live="polite">
      {toasts.map((item) => (
        <div className={`toast ${item.tone}`} key={item.id}>
          <Icon name={item.tone === "success" ? "check" : item.tone === "error" ? "alert" : "info"} />
          <p>{item.text}</p>
          <button type="button" aria-label="关闭提示" onClick={() => dismiss(item.id)}><Icon name="x" size={14} /></button>
        </div>
      ))}
    </div>
  );
}
