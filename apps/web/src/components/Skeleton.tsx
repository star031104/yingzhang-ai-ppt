import type { CSSProperties } from "react";

export function Skeleton({ width, height = 12, radius, className = "" }: { width?: number | string; height?: number | string; radius?: number; className?: string }) {
  const style: CSSProperties = { width, height, borderRadius: radius };
  return <span className={`skeleton ${className}`} style={style} aria-hidden="true" />;
}

export function SkeletonLines({ lines = 3 }: { lines?: number }) {
  return (
    <div className="skeleton-block" aria-hidden="true">
      {Array.from({ length: lines }, (_, index) => (
        <Skeleton key={index} className="skeleton-text" width={`${index === lines - 1 ? 60 : 100 - index * 8}%`} />
      ))}
    </div>
  );
}
