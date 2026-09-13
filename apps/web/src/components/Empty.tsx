export function Empty({ title, text }: { title: string; text: string }) {
  return (
    <div className="empty">
      <span>◇</span>
      <h4>{title}</h4>
      <p>{text}</p>
    </div>
  );
}
