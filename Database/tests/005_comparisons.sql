BEGIN;
SET LOCAL plpgsql.check_asserts = on;

DO $$
DECLARE
    target_a UUID;
    target_b UUID;
    saved_id UUID;
    review_a UUID;
    review_b UUID;
BEGIN
    INSERT INTO public.analysis_targets(owner_clerk_id, google_place_id, business_name, source_url)
        VALUES ('comparison-test', 'cmp-place-a', 'A', 'https://google.com/a') RETURNING id INTO target_a;
    INSERT INTO public.analysis_targets(owner_clerk_id, google_place_id, business_name, source_url)
        VALUES ('comparison-test', 'cmp-place-b', 'B', 'https://google.com/b') RETURNING id INTO target_b;
    INSERT INTO public.reviews(analysis_target_id, rating, review_text)
        VALUES (target_a, 5, 'Review A') RETURNING id INTO review_a;
    INSERT INTO public.reviews(analysis_target_id, rating, review_text)
        VALUES (target_b, 3, 'Review B') RETURNING id INTO review_b;
    INSERT INTO public.comparisons(owner_clerk_id, name, target_a_id, target_b_id)
        VALUES ('comparison-test', 'A vs B', target_a, target_b) RETURNING id INTO saved_id;

    DELETE FROM public.comparisons WHERE id = saved_id;
    ASSERT NOT EXISTS (SELECT 1 FROM public.comparisons WHERE id = saved_id);
    ASSERT (SELECT count(*) = 2 FROM public.analysis_targets WHERE id IN (target_a, target_b)), 'Deleting a comparison removed targets';
    ASSERT (SELECT count(*) = 2 FROM public.reviews WHERE id IN (review_a, review_b)), 'Deleting a comparison removed reviews';

    INSERT INTO public.comparisons(owner_clerk_id, name, target_a_id, target_b_id)
        VALUES ('comparison-test', 'A vs B', target_a, target_b) RETURNING id INTO saved_id;
    DELETE FROM public.analysis_targets WHERE id = target_a;
    ASSERT (SELECT target_a_id IS NULL AND target_b_id = target_b FROM public.comparisons WHERE id = saved_id), 'Deleted target A did not leave an unavailable reference';
    ASSERT EXISTS (SELECT 1 FROM public.reviews WHERE id = review_b), 'Target A deletion affected target B';
    DELETE FROM public.analysis_targets WHERE id = target_b;
    ASSERT (SELECT target_a_id IS NULL AND target_b_id IS NULL FROM public.comparisons WHERE id = saved_id), 'Deleted targets removed the saved comparison';

    ASSERT (SELECT relrowsecurity FROM pg_class WHERE oid = 'public.comparisons'::regclass);
    ASSERT has_table_privilege('service_role', 'public.comparisons', 'SELECT,INSERT,UPDATE,DELETE');
END;
$$;

ROLLBACK;
