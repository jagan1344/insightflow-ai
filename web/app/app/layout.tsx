import { ReactNode } from "react";
import { Sidebar } from "@/components/shell/Sidebar";

export default function AppLayout({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-bg text-ink grid md:grid-cols-[14rem_1fr]">
      <Sidebar />
      <main className="min-w-0 min-h-screen flex flex-col">{children}</main>
    </div>
  );
}
