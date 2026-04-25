import { type ReactNode } from "react";
import { cn } from "@/lib/utils";

interface Props {
  title: ReactNode;
  description?: ReactNode;
  className?: string;
  action?: ReactNode;
}

export function Empty({ title, description, className, action }: Props) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-2 rounded-md border border-dashed border-border p-6 text-center text-sm text-muted-foreground",
        className,
      )}
    >
      <div className="font-medium text-foreground">{title}</div>
      {description && <p>{description}</p>}
      {action}
    </div>
  );
}
