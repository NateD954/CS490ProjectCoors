BEGIN;

CREATE TABLE IF NOT EXISTS public.comparisons (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_clerk_id TEXT NOT NULL,
    name TEXT NOT NULL,
    target_a_id UUID REFERENCES public.analysis_targets(id) ON DELETE SET NULL,
    target_b_id UUID REFERENCES public.analysis_targets(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (target_a_id <> target_b_id)
);

CREATE INDEX IF NOT EXISTS idx_comparisons_owner_created
    ON public.comparisons(owner_clerk_id, created_at DESC);

ALTER TABLE public.comparisons ENABLE ROW LEVEL SECURITY;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.comparisons TO service_role;

COMMIT;
