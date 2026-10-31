-- S1-014: store the platform and source URL on analysis_targets.
-- Run once in the Supabase SQL editor.
 
ALTER TABLE public.analysis_targets
    ADD COLUMN IF NOT EXISTS platform TEXT NOT NULL DEFAULT 'GOOGLE_MAPS'
        CHECK (platform IN ('GOOGLE_MAPS')),
    ADD COLUMN IF NOT EXISTS source_url TEXT;
 
-- Existing rows have no URL; backfill so NOT NULL can apply.
UPDATE public.analysis_targets SET source_url = '' WHERE source_url IS NULL;
ALTER TABLE public.analysis_targets ALTER COLUMN source_url SET NOT NULL;
 