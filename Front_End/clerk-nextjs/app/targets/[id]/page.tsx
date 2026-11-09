import { Suspense } from "react";
import { ToastProvider } from "@/components/ui/Toast";
import { TargetWorkspace } from "@/components/TargetWorkspace";
import { Spinner } from "@/components/ui/Spinner";
import ReviewQA from "@/components/ReviewQA";

// Reading `params` is request-time data, so Next.js wants it inside <Suspense>.
async function WorkspaceLoader({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return (
    <div className="flex flex-col gap-8">
      <TargetWorkspace id={id} />
      <ReviewQA targetId={id} />
    </div>
  );
}

export default function TargetPage({ params }: { params: Promise<{ id: string }> }) {
  return (
    <ToastProvider>
      <main className="mx-auto w-full max-w-4xl flex-1 px-4 pb-16 pt-4 text-zinc-100">
        <Suspense
          fallback={
            <div className="flex items-center gap-3 text-zinc-400">
              <Spinner /> Loading workspace…
            </div>
          }
        >
          <WorkspaceLoader params={params} />
        </Suspense>
      </main>
    </ToastProvider>
  );
}
