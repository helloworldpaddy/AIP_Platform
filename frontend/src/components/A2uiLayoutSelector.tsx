import {
  A2UI_LAYOUT_OPTIONS,
  getA2uiLayoutPreference,
  setA2uiLayoutPreference,
  type A2uiLayoutId,
} from "@/lib/a2ui-layout-preference";
import { cn } from "@/lib/utils";

type Props = {
  value: A2uiLayoutId;
  onChange: (layout: A2uiLayoutId) => void;
  className?: string;
};

export function A2uiLayoutSelector({ value, onChange, className }: Props) {
  return (
    <div className={cn("space-y-2", className)}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-xs font-medium text-muted-foreground">Summary layout</span>
        <span className="text-[10px] text-muted-foreground">
          Applies to Interactive summary — does not change chat text
        </span>
      </div>
      <div className="grid gap-2 sm:grid-cols-2">
        {A2UI_LAYOUT_OPTIONS.map((opt) => (
          <button
            key={opt.id}
            type="button"
            onClick={() => {
              setA2uiLayoutPreference(opt.id);
              onChange(opt.id);
            }}
            className={cn(
              "rounded-md border px-3 py-2 text-left transition-colors",
              value === opt.id
                ? "border-primary bg-primary/10 ring-1 ring-primary/30"
                : "border-border bg-card/50 hover:border-primary/25",
            )}
          >
            <span className="text-xs font-medium">{opt.label}</span>
            <p className="mt-0.5 text-[10px] leading-snug text-muted-foreground">
              {opt.description}
            </p>
          </button>
        ))}
      </div>
    </div>
  );
}

export function useA2uiLayoutPreference(): A2uiLayoutId {
  return getA2uiLayoutPreference();
}
