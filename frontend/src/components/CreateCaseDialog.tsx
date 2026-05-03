import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { casesApi, ApiError } from "@/lib/api";
import type { CasePriority, LineOfBusiness } from "@/lib/types";
import { getAnalystId } from "@/lib/analyst";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";

interface Props {
  open: boolean;
  onClose: () => void;
}

const PRIORITIES: CasePriority[] = ["LOW", "MEDIUM", "HIGH", "CRITICAL"];

const LINES_OF_BUSINESS: { value: LineOfBusiness; label: string }[] = [
  { value: "CARDS", label: "Cards" },
  { value: "RETAIL_BANKING", label: "Retail banking" },
  { value: "SERVICES", label: "Services" },
];

export function CreateCaseDialog({ open, onClose }: Props) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [caseNumber, setCaseNumber] = useState(
    () => `AML-${new Date().getFullYear()}-${String(Math.floor(Math.random() * 1_000_000)).padStart(6, "0")}`,
  );
  const [alertType, setAlertType] = useState("TRANSACTION_MONITORING");
  const [subjectId, setSubjectId] = useState("");
  const [subjectName, setSubjectName] = useState("");
  const [priority, setPriority] = useState<CasePriority>("MEDIUM");
  const [lineOfBusiness, setLineOfBusiness] = useState<LineOfBusiness>("RETAIL_BANKING");
  const [alertPayload, setAlertPayload] = useState("{\n  \n}");
  const [error, setError] = useState<string | null>(null);

  const create = useMutation({
    mutationFn: () => {
      let payload: Record<string, unknown> = {};
      try {
        payload = alertPayload.trim() ? JSON.parse(alertPayload) : {};
      } catch (e) {
        throw new Error(`Invalid alert_payload JSON: ${(e as Error).message}`);
      }
      return casesApi.create({
        case_number: caseNumber.trim(),
        alert_type: alertType.trim(),
        alert_payload: payload,
        subject_party_id: subjectId.trim(),
        subject_party_name: subjectName.trim(),
        line_of_business: lineOfBusiness,
        priority,
        created_by: getAnalystId() || "system",
      });
    },
    onSuccess: (created) => {
      qc.invalidateQueries({ queryKey: ["cases"] });
      onClose();
      navigate(`/cases/${created.id}`);
    },
    onError: (err) => {
      setError(err instanceof ApiError ? `${err.status} · ${err.message}` : (err as Error).message);
    },
  });

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Create new case"
      description="Cases are immutable once their narrative is submitted, so capture the alert basics now."
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button
            onClick={() => {
              setError(null);
              create.mutate();
            }}
            disabled={create.isPending || !caseNumber || !subjectId || !subjectName}
          >
            {create.isPending ? "Creating…" : "Create case"}
          </Button>
        </>
      }
    >
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Field label="Case number">
          <Input value={caseNumber} onChange={(e) => setCaseNumber(e.target.value)} />
        </Field>
        <Field label="Alert type">
          <Input value={alertType} onChange={(e) => setAlertType(e.target.value)} />
        </Field>
        <Field label="Subject party id">
          <Input value={subjectId} onChange={(e) => setSubjectId(e.target.value)} />
        </Field>
        <Field label="Subject party name">
          <Input value={subjectName} onChange={(e) => setSubjectName(e.target.value)} />
        </Field>
        <Field label="Priority">
          <Select value={priority} onChange={(e) => setPriority(e.target.value as CasePriority)}>
            {PRIORITIES.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Line of business">
          <Select
            value={lineOfBusiness}
            onChange={(e) => setLineOfBusiness(e.target.value as LineOfBusiness)}
          >
            {LINES_OF_BUSINESS.map((lob) => (
              <option key={lob.value} value={lob.value}>
                {lob.label}
              </option>
            ))}
          </Select>
        </Field>
      </div>
      <div className="mt-3">
        <Field label="Alert payload (JSON)">
          <Textarea
            value={alertPayload}
            onChange={(e) => setAlertPayload(e.target.value)}
            className="font-mono text-xs"
            rows={6}
          />
        </Field>
      </div>
      {error && (
        <div className="mt-3 rounded-md border border-destructive/40 bg-destructive/5 p-2 text-xs text-destructive">
          {error}
        </div>
      )}
    </Dialog>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        {label}
      </span>
      <div className="mt-1">{children}</div>
    </label>
  );
}
