import { useEffect, useState } from "react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { getAnalystId, setAnalystId, subscribeAnalystId } from "@/lib/analyst";
import { UserCircle2 } from "lucide-react";

export function AnalystBar() {
  const [draft, setDraft] = useState(getAnalystId());
  const [saved, setSaved] = useState(getAnalystId());

  useEffect(() => {
    return subscribeAnalystId(() => {
      const v = getAnalystId();
      setSaved(v);
      setDraft(v);
    });
  }, []);

  const apply = () => {
    const v = draft.trim();
    setAnalystId(v);
    setSaved(v);
  };

  return (
    <div className="flex items-center gap-2">
      <UserCircle2 className="h-4 w-4 text-muted-foreground" />
      <Input
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") apply();
        }}
        placeholder="X-Analyst-Id (e.g. analyst.jane)"
        className="h-8 w-64"
      />
      <Button
        size="sm"
        variant={draft.trim() === saved ? "secondary" : "default"}
        onClick={apply}
        disabled={!draft.trim() || draft.trim() === saved}
      >
        {draft.trim() === saved ? "Set" : "Save"}
      </Button>
    </div>
  );
}
