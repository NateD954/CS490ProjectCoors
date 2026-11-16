BEGIN;

CREATE OR REPLACE FUNCTION public.get_target_review_summary(target_id UUID)
RETURNS TABLE (review_count BIGINT, average_rating NUMERIC)
LANGUAGE sql STABLE SECURITY INVOKER SET search_path = ''
AS $$
    SELECT COUNT(*), AVG(r.rating)
    FROM public.reviews AS r
    WHERE r.analysis_target_id = target_id;
$$;

-- The backend verifies the Clerk owner before calling this function.
REVOKE EXECUTE ON FUNCTION public.get_target_review_summary(UUID) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.get_target_review_summary(UUID) TO service_role;

COMMIT;
