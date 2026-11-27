BEGIN;

-- use the source id, or a text/rating/date fingerprint if it's missing
CREATE OR REPLACE FUNCTION public.review_identity(
    source_id TEXT, stars INTEGER, body TEXT, source_date TIMESTAMPTZ
)
RETURNS TEXT
LANGUAGE sql IMMUTABLE SET search_path = ''
AS $$
    SELECT CASE WHEN NULLIF(btrim(source_id), '') IS NOT NULL
        THEN 'source:' || btrim(source_id)
        ELSE 'fingerprint:v1:' || encode(sha256(convert_to(
            jsonb_build_array(
                lower(btrim(regexp_replace(COALESCE(body, ''), '[[:space:]]+', ' ', 'g'))),
                stars,
                extract(epoch FROM source_date)
            )::TEXT, 'UTF8'
        )), 'hex')
    END;
$$;

ALTER TABLE public.reviews
    ADD COLUMN IF NOT EXISTS review_key TEXT GENERATED ALWAYS AS (
        public.review_identity(google_review_id, rating, review_text, reviewed_at)
    ) STORED;

-- clean up old copies before adding the missing-id guard
DELETE FROM public.reviews
WHERE id IN (
    SELECT id FROM (
        SELECT id, row_number() OVER (
            PARTITION BY analysis_target_id, review_key
            ORDER BY ingested_at DESC, id
        ) AS copy_number
        FROM public.reviews
    ) copies WHERE copy_number > 1
);

CREATE UNIQUE INDEX IF NOT EXISTS reviews_target_review_key
    ON public.reviews(analysis_target_id, review_key);

ALTER TABLE public.analysis_targets
    ADD COLUMN IF NOT EXISTS current_ingestion_id UUID REFERENCES public.ingestion_jobs(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS current_ingestion_at TIMESTAMPTZ;

UPDATE public.analysis_targets t
SET current_ingestion_id = last_good.id,
    current_ingestion_at = COALESCE(last_good.completed_at, last_good.created_at)
FROM (
    SELECT DISTINCT ON (analysis_target_id) id, analysis_target_id, completed_at, created_at
    FROM public.ingestion_jobs
    WHERE status = 'completed'
    ORDER BY analysis_target_id, completed_at DESC NULLS LAST, created_at DESC, id
) last_good
WHERE t.id = last_good.analysis_target_id AND t.current_ingestion_id IS NULL;

-- stop the backend before running this migration
UPDATE public.ingestion_jobs
SET status = 'failed', completed_at = now(),
    error_message = 'Ingestion did not finish. You can try again.'
WHERE status IN ('pending', 'running');

CREATE UNIQUE INDEX IF NOT EXISTS ingestion_jobs_one_active_target
    ON public.ingestion_jobs(analysis_target_id)
    WHERE status IN ('pending', 'running');

CREATE OR REPLACE FUNCTION public.begin_review_ingestion(p_target_id UUID)
RETURNS SETOF public.ingestion_jobs
LANGUAGE plpgsql SECURITY INVOKER SET search_path = ''
AS $$
BEGIN
    PERFORM 1 FROM public.analysis_targets WHERE id = p_target_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Target not found.' USING ERRCODE = 'P0002';
    END IF;

    UPDATE public.ingestion_jobs
    SET status = 'failed', completed_at = now(),
        error_message = 'Ingestion did not finish. You can try again.'
    WHERE analysis_target_id = p_target_id AND status IN ('pending', 'running')
        AND COALESCE(started_at, created_at) < now() - interval '10 minutes';

    IF EXISTS (
        SELECT 1 FROM public.ingestion_jobs
        WHERE analysis_target_id = p_target_id AND status IN ('pending', 'running')
    ) THEN
        RAISE EXCEPTION 'Ingestion is already running for this target.' USING ERRCODE = '55P03';
    END IF;

    RETURN QUERY INSERT INTO public.ingestion_jobs(analysis_target_id, status, started_at)
        VALUES (p_target_id, 'running', now()) RETURNING *;
END;
$$;

CREATE OR REPLACE FUNCTION public.complete_review_ingestion(
    p_target_id UUID, p_job_id UUID, p_reviews JSONB, p_skipped INTEGER
)
RETURNS SETOF public.ingestion_jobs
LANGUAGE plpgsql SECURITY INVOKER SET search_path = ''
AS $$
DECLARE
    saved_job public.ingestion_jobs;
    saved_count INTEGER;
BEGIN
    PERFORM 1 FROM public.analysis_targets WHERE id = p_target_id FOR UPDATE;
    SELECT * INTO saved_job FROM public.ingestion_jobs
        WHERE id = p_job_id AND analysis_target_id = p_target_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Ingestion attempt not found.';
    END IF;
    IF saved_job.status = 'completed' THEN
        RETURN NEXT saved_job;
        RETURN;
    END IF;
    IF saved_job.status <> 'running'
        OR COALESCE(saved_job.started_at, saved_job.created_at) < now() - interval '10 minutes' THEN
        RAISE EXCEPTION 'Ingestion attempt is no longer active.';
    END IF;
    IF p_reviews IS NULL OR jsonb_typeof(p_reviews) <> 'array'
        OR p_skipped IS NULL OR p_skipped < 0 THEN
        RAISE EXCEPTION 'Invalid ingestion batch.';
    END IF;

    INSERT INTO public.reviews(analysis_target_id, google_review_id, rating, review_text, reviewed_at)
    SELECT p_target_id, r.google_review_id, r.rating, r.review_text, r.reviewed_at
    FROM (
        SELECT DISTINCT ON (public.review_identity(x.google_review_id, x.rating, x.review_text, x.reviewed_at))
            x.*, batch.position
        FROM jsonb_array_elements(p_reviews) WITH ORDINALITY AS batch(value, position)
        CROSS JOIN LATERAL jsonb_to_record(batch.value) AS x(
            google_review_id TEXT, rating INTEGER, review_text TEXT, reviewed_at TIMESTAMPTZ
        )
        ORDER BY public.review_identity(x.google_review_id, x.rating, x.review_text, x.reviewed_at), batch.position
    ) r
    ON CONFLICT (analysis_target_id, review_key) DO UPDATE
        SET google_review_id = EXCLUDED.google_review_id,
            rating = EXCLUDED.rating,
            review_text = EXCLUDED.review_text,
            reviewed_at = EXCLUDED.reviewed_at,
            ingested_at = now();
    GET DIAGNOSTICS saved_count = ROW_COUNT;

    UPDATE public.ingestion_jobs
    SET status = 'completed', reviews_ingested = saved_count,
        reviews_skipped = p_skipped + jsonb_array_length(p_reviews) - saved_count,
        completed_at = now(), error_message = NULL
    WHERE id = p_job_id RETURNING * INTO saved_job;

    UPDATE public.analysis_targets
    SET current_ingestion_id = p_job_id, current_ingestion_at = saved_job.completed_at
    WHERE id = p_target_id;

    RETURN NEXT saved_job;
END;
$$;

REVOKE EXECUTE ON FUNCTION public.begin_review_ingestion(UUID) FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.complete_review_ingestion(UUID, UUID, JSONB, INTEGER) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.begin_review_ingestion(UUID) TO service_role;
GRANT EXECUTE ON FUNCTION public.complete_review_ingestion(UUID, UUID, JSONB, INTEGER) TO service_role;

COMMIT;
