ALTER TABLE public.ingestion_jobs
    ADD COLUMN IF NOT EXISTS reviews_skipped INTEGER CHECK (reviews_skipped >= 0);
