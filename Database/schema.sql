-- ============================================
-- Database Schema
-- CS490 - Team Coors
-- Database: Supabase PostgreSQL
-- ============================================


-- ============================================
-- 1. Analysis Targets
-- ============================================

CREATE TABLE public.analysis_targets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    owner_clerk_id TEXT NOT NULL,

    google_place_id TEXT NOT NULL,

    business_name TEXT NOT NULL,

    platform TEXT NOT NULL DEFAULT 'GOOGLE_MAPS'
        CHECK (platform IN ('GOOGLE_MAPS')),

    source_url TEXT NOT NULL,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_analysis_targets_owner
ON public.analysis_targets(owner_clerk_id);

ALTER TABLE public.analysis_targets
ENABLE ROW LEVEL SECURITY;



-- ============================================
-- 2. Reviews
-- ============================================

CREATE TABLE public.reviews (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    analysis_target_id UUID NOT NULL
        REFERENCES public.analysis_targets(id)
        ON DELETE CASCADE,

    google_review_id TEXT,

    rating INTEGER NOT NULL
        CHECK (rating BETWEEN 1 AND 5),

    review_text TEXT,

    reviewed_at TIMESTAMPTZ,

    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (analysis_target_id, google_review_id)
);

CREATE INDEX idx_reviews_target
ON public.reviews(analysis_target_id);

ALTER TABLE public.reviews
ENABLE ROW LEVEL SECURITY;



-- ============================================
-- 3. Ingestion Jobs
-- ============================================

CREATE TABLE public.ingestion_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    analysis_target_id UUID NOT NULL
        REFERENCES public.analysis_targets(id)
        ON DELETE CASCADE,

    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (
            status IN (
                'pending',
                'running',
                'completed',
                'failed'
            )
        ),

    reviews_ingested INTEGER NOT NULL DEFAULT 0
        CHECK (reviews_ingested >= 0),

    error_message TEXT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    started_at TIMESTAMPTZ,

    completed_at TIMESTAMPTZ
);

CREATE INDEX idx_ingestion_jobs_target
ON public.ingestion_jobs(analysis_target_id);

ALTER TABLE public.ingestion_jobs
ENABLE ROW LEVEL SECURITY;