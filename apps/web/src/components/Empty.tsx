import type { ReactNode } from "react";
import { Icon } from "./Icon";
import type { IconName } from "./Icon";

export function Empty({ title, text, icon = "layers", action }: { title: string; text: string; icon?: IconName; action?: ReactNode }) {
  return (
    <div className="empty">
      <span><Icon name={icon} size={20} /></span>
      <h4>{title}</h4>
      <p>{text}</p>
      {action && <div className="empty-action">{action}</div>}
    </div>
  );
}
