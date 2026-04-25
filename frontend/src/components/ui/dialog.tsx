import { useEffect, type ReactNode } from "react";
import { cn } from "@/lib/utils";

interface DialogProps {
  open: boolean;
  onClose: () => void;
  title?: ReactNode;
  description?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  className?: string;
}

export function Dialog({
  open,
  onClose,
  title,
  description,
  children,
  footer,
  className,
}: DialogProps) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.body.classList.add("overflow-hidden");
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.classList.remove("overflow-hidden");
      window.removeEventListener("keydown", onKey);
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        className={cn(
          "max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-lg border border-border bg-card text-card-foreground shadow-xl",
          className,
        )}
        onClick={(e) => e.stopPropagation()}
      >
        {(title || description) && (
          <div className="border-b border-border p-4 sm:p-6">
            {title && (
              <h2 className="text-lg font-semibold leading-none tracking-tight">
                {title}
              </h2>
            )}
            {description && (
              <p className="mt-2 text-sm text-muted-foreground">{description}</p>
            )}
          </div>
        )}
        <div className="p-4 sm:p-6">{children}</div>
        {footer && (
          <div className="flex items-center justify-end gap-2 border-t border-border p-4 sm:p-6">
            {footer}
          </div>
        )}
      </div>
    </div>
  );
}
