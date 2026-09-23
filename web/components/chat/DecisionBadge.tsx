import { Badge } from "@/components/ui/Badge";
import type { DecisionAction } from "@/lib/types";
import { CheckCircle2, AlertTriangle, HelpCircle, XCircle } from "lucide-react";

const ICONS: Record<DecisionAction, React.ReactNode> = {
  ANSWER:  <CheckCircle2 size={12} />,
  WARN:    <AlertTriangle size={12} />,
  CLARIFY: <HelpCircle size={12} />,
  ABSTAIN: <XCircle size={12} />,
};

const TONES: Record<DecisionAction, "answer" | "warn" | "clarify" | "abstain"> = {
  ANSWER: "answer", WARN: "warn", CLARIFY: "clarify", ABSTAIN: "abstain",
};

export function DecisionBadge({ action, score }: { action: DecisionAction; score: number }) {
  return (
    <Badge tone={TONES[action]}>
      {ICONS[action]} {action} · {score.toFixed(2)}
    </Badge>
  );
}
