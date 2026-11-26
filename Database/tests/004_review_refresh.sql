BEGIN;

SET LOCAL plpgsql.check_asserts = on;

CREATE FUNCTION pg_temp.reject_refresh_promotion()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF current_setting('reviewlens.test_promotion_failure', true) = 'on' THEN
        RAISE EXCEPTION 'Test promotion failure';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER test_refresh_promotion_failure
    BEFORE UPDATE ON public.analysis_targets
    FOR EACH ROW EXECUTE FUNCTION pg_temp.reject_refresh_promotion();

DO $$
DECLARE
    target_id UUID;
    other_target UUID;
    first_job public.ingestion_jobs;
    refresh_job public.ingestion_jobs;
    result_job public.ingestion_jobs;
    original_review UUID;
    saved_version UUID;
    saved_reviews JSONB;
    rejected BOOLEAN;
BEGIN
    INSERT INTO public.analysis_targets(owner_clerk_id, google_place_id, business_name, source_url)
        VALUES ('refresh-test', 'place-a', 'Refresh test', 'https://google.com') RETURNING id INTO target_id;
    INSERT INTO public.analysis_targets(owner_clerk_id, google_place_id, business_name, source_url)
        VALUES ('refresh-test', 'place-b', 'Other test', 'https://google.com') RETURNING id INTO other_target;

    SELECT * INTO first_job FROM public.begin_review_ingestion(target_id);
    PERFORM public.complete_review_ingestion(target_id, first_job.id, '[
        {"google_review_id":"r1","rating":5,"review_text":"Original","reviewed_at":"2026-11-01T00:00:00Z"},
        {"google_review_id":"r2","rating":3,"review_text":"Retained","reviewed_at":null},
        {"google_review_id":null,"rating":4,"review_text":"No source id","reviewed_at":"2026-11-02T00:00:00Z"}
    ]', 0);
    SELECT id INTO original_review FROM public.reviews
        WHERE analysis_target_id = target_id AND google_review_id = 'r1';

    SELECT * INTO refresh_job FROM public.begin_review_ingestion(target_id);
    SELECT * INTO result_job FROM public.complete_review_ingestion(target_id, refresh_job.id, '[
        {"google_review_id":"r1","rating":1,"review_text":"Edited","reviewed_at":"2026-11-03T00:00:00Z"},
        {"google_review_id":"r3","rating":5,"review_text":"New review","reviewed_at":null},
        {"google_review_id":null,"rating":4,"review_text":"  NO   source ID  ","reviewed_at":"2026-11-01T19:00:00-05:00"},
        {"google_review_id":null,"rating":4,"review_text":"No source id","reviewed_at":"2026-11-02T00:00:00Z"},
        {"google_review_id":"r1","rating":2,"review_text":"Duplicate in batch","reviewed_at":null}
    ]', 2);
    ASSERT result_job.status = 'completed' AND result_job.reviews_ingested = 3;
    ASSERT result_job.reviews_skipped = 4;
    ASSERT (SELECT count(*) = 4 FROM public.reviews WHERE analysis_target_id = target_id), 'Partial refresh lost reviews or created copies';
    ASSERT (SELECT id = original_review AND rating = 1 AND review_text = 'Edited'
        FROM public.reviews WHERE analysis_target_id = target_id AND google_review_id = 'r1'), 'Stable-id edit was not reconciled';
    ASSERT (SELECT review_count = 4 AND average_rating = 3.25 FROM public.get_target_review_summary(target_id));
    ASSERT (SELECT current_ingestion_id = refresh_job.id FROM public.analysis_targets WHERE id = target_id);
    saved_version := refresh_job.id;

    PERFORM public.complete_review_ingestion(target_id, refresh_job.id, '[]', 0);
    ASSERT (SELECT reviews_ingested = 3 FROM public.ingestion_jobs WHERE id = refresh_job.id), 'Retry changed a completed job';
    ASSERT (SELECT count(*) = 4 FROM public.reviews WHERE analysis_target_id = target_id);

    SELECT * INTO first_job FROM public.begin_review_ingestion(other_target);
    PERFORM public.complete_review_ingestion(other_target, first_job.id,
        '[{"google_review_id":"r1","rating":5,"review_text":"Other target"}]', 0);
    ASSERT (SELECT count(*) = 1 FROM public.reviews WHERE analysis_target_id = other_target), 'Identities leaked between targets';

    SELECT jsonb_agg(to_jsonb(r) ORDER BY r.id) INTO saved_reviews FROM public.reviews r WHERE analysis_target_id = target_id;
    SELECT * INTO refresh_job FROM public.begin_review_ingestion(target_id);
    rejected := FALSE;
    BEGIN
        PERFORM public.begin_review_ingestion(target_id);
    EXCEPTION WHEN lock_not_available THEN
        rejected := TRUE;
    END;
    ASSERT rejected, 'Overlapping ingestion was allowed';
    ASSERT (SELECT current_ingestion_id = saved_version FROM public.analysis_targets WHERE id = target_id);

    rejected := FALSE;
    BEGIN
        PERFORM public.complete_review_ingestion(target_id, refresh_job.id, '[
            {"google_review_id":"r1","rating":2,"review_text":"Must roll back"},
            {"google_review_id":"new-invalid","rating":8,"review_text":"Invalid rating"}
        ]', 0);
    EXCEPTION WHEN check_violation THEN
        rejected := TRUE;
    END;
    ASSERT rejected, 'Invalid batch was accepted';
    ASSERT (SELECT jsonb_agg(to_jsonb(r) ORDER BY r.id) = saved_reviews FROM public.reviews r WHERE analysis_target_id = target_id), 'Failed batch changed the dataset';
    ASSERT (SELECT current_ingestion_id = saved_version FROM public.analysis_targets WHERE id = target_id);
    ASSERT (SELECT status = 'running' FROM public.ingestion_jobs WHERE id = refresh_job.id);

    PERFORM set_config('reviewlens.test_promotion_failure', 'on', true);
    rejected := FALSE;
    BEGIN
        PERFORM public.complete_review_ingestion(target_id, refresh_job.id,
            '[{"google_review_id":"r1","rating":2,"review_text":"Must also roll back"}]', 0);
    EXCEPTION WHEN raise_exception THEN
        rejected := TRUE;
    END;
    PERFORM set_config('reviewlens.test_promotion_failure', 'off', true);
    ASSERT rejected, 'Promotion failure was not triggered';
    ASSERT (SELECT jsonb_agg(to_jsonb(r) ORDER BY r.id) = saved_reviews FROM public.reviews r WHERE analysis_target_id = target_id), 'Promotion error left changed reviews';
    ASSERT (SELECT status = 'running' FROM public.ingestion_jobs WHERE id = refresh_job.id), 'Promotion error committed the job';
    ASSERT (SELECT current_ingestion_id = saved_version FROM public.analysis_targets WHERE id = target_id);

    UPDATE public.ingestion_jobs SET status = 'failed', error_message = 'Test failure' WHERE id = refresh_job.id;
    rejected := FALSE;
    BEGIN
        PERFORM public.complete_review_ingestion(target_id, refresh_job.id, '[]', 0);
    EXCEPTION WHEN raise_exception THEN
        rejected := TRUE;
    END;
    ASSERT rejected, 'Failed attempt was promoted';

    SELECT * INTO refresh_job FROM public.begin_review_ingestion(target_id);
    UPDATE public.ingestion_jobs SET started_at = now() - interval '11 minutes' WHERE id = refresh_job.id;
    SELECT * INTO first_job FROM public.begin_review_ingestion(target_id);
    ASSERT (SELECT status = 'failed' FROM public.ingestion_jobs WHERE id = refresh_job.id), 'Stale attempt was not expired';
    rejected := FALSE;
    BEGIN
        PERFORM public.complete_review_ingestion(target_id, refresh_job.id, '[]', 0);
    EXCEPTION WHEN raise_exception THEN
        rejected := TRUE;
    END;
    ASSERT rejected, 'Old attempt overwrote a newer attempt';

    PERFORM public.complete_review_ingestion(target_id, first_job.id, '[]', 0);
    ASSERT (SELECT jsonb_agg(to_jsonb(r) ORDER BY r.id) = saved_reviews FROM public.reviews r WHERE analysis_target_id = target_id), 'Empty response changed the dataset';
    ASSERT (SELECT current_ingestion_id = first_job.id FROM public.analysis_targets WHERE id = target_id);

    ASSERT public.review_identity(NULL, 5, E'\n GREAT\t place \r', NULL)
        = public.review_identity('', 5, 'great place', NULL), 'Fallback normalization differs';
    ASSERT public.review_identity(NULL, 5, 'Same text', NULL)
        <> public.review_identity(NULL, 4, 'Same text', NULL), 'Distinct fallback attributes collided';
    ASSERT NOT has_function_privilege('anon', 'public.begin_review_ingestion(uuid)', 'EXECUTE');
    ASSERT NOT has_function_privilege('authenticated', 'public.complete_review_ingestion(uuid,uuid,jsonb,integer)', 'EXECUTE');
    ASSERT has_function_privilege('service_role', 'public.complete_review_ingestion(uuid,uuid,jsonb,integer)', 'EXECUTE');
END;
$$;

ROLLBACK;
