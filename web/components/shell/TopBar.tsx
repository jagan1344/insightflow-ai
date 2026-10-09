"use client";

import { useState } from "react";
import { Upload } from "lucide-react";

import { Button } from "@/components/ui/Button";
import { LiveIndicator } from "@/components/dashboard/LiveIndicator";
import { DatasetPicker } from "@/components/dashboard/DatasetPicker";
import { UploadDialog } from "@/components/dashboard/UploadDialog";

export function TopBar({ title, subtitle, live, updatedAt }: {
  title: string;
  subtitle?: string;
  live?: boolean;
  updatedAt?: number | null;
  version?: number;      // accepted for backward compat; ignored by LiveIndicator
}) {
  const [uploadOpen, setUploadOpen] = useState(false);
  return (
    <header className="h-14 flex items-center gap-3 px-4 border-b border-panel-border bg-bg">
      <div className="flex-1 min-w-0">
        <div className="text-sm font-semibold text-ink truncate">{title}</div>
        {subtitle && (
          <div className="text-xs text-ink-muted truncate">{subtitle}</div>
        )}
      </div>
      <LiveIndicator live={!!live} updatedAt={updatedAt ?? null} />
      <DatasetPicker />
      <Button variant="secondary" onClick={() => setUploadOpen(true)}>
        <Upload size={14} /> Upload
      </Button>
      <UploadDialog open={uploadOpen} onClose={() => setUploadOpen(false)}
                    onSuccess={() => {}} />
    </header>
  );
}
