BEGIN;

-- S3-013: the reviews that support each saved answer. Only the ids are kept here;
-- the text and rating are always read from public.reviews.
ALTER TABLE public.qa_history
    ADD COLUMN IF NOT EXISTS supporting_review_ids UUID[] NOT NULL DEFAULT '{}';

COMMIT;
