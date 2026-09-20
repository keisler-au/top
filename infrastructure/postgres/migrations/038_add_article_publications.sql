BEGIN;

-- PW-WP2a: this is the minimal public projection.  It deliberately contains
-- only immutable article-revision and batch-theme snapshots; source evidence,
-- editorial history, and generation data stay in their private relations.
CREATE TABLE article_publications (
    article_id BIGINT PRIMARY KEY
        REFERENCES articles(id) ON DELETE CASCADE,
    approved_revision_id BIGINT NOT NULL,
    slug TEXT NOT NULL
        CONSTRAINT article_publications_slug_nonempty
        CHECK (btrim(slug) <> '' AND char_length(slug) <= 180),
    first_published_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT article_publications_slug_unique UNIQUE (slug),
    CONSTRAINT article_publications_revision_belongs_to_article
        FOREIGN KEY (article_id, approved_revision_id)
        REFERENCES article_revisions(article_id, id) ON DELETE RESTRICT
);

CREATE INDEX idx_article_publications_updated
    ON article_publications(updated_at DESC, article_id DESC);

CREATE TABLE article_publication_themes (
    article_id BIGINT NOT NULL
        REFERENCES article_publications(article_id) ON DELETE CASCADE,
    approved_revision_id BIGINT NOT NULL,
    stable_theme_id BIGINT NOT NULL
        REFERENCES theme_identities(id) ON DELETE RESTRICT,
    display_name TEXT NOT NULL
        CONSTRAINT article_publication_themes_display_name_nonempty
        CHECK (btrim(display_name) <> '' AND char_length(display_name) <= 120),
    PRIMARY KEY (article_id, approved_revision_id, stable_theme_id),
    CONSTRAINT article_publication_themes_revision_belongs_to_article
        FOREIGN KEY (article_id, approved_revision_id)
        REFERENCES article_revisions(article_id, id) ON DELETE RESTRICT
);

CREATE INDEX idx_article_publication_themes_theme
    ON article_publication_themes(stable_theme_id, article_id, approved_revision_id);

CREATE OR REPLACE FUNCTION public_article_slug(article_title TEXT, article_id BIGINT)
RETURNS TEXT LANGUAGE sql IMMUTABLE STRICT AS $$
    SELECT COALESCE(NULLIF(left(
        trim(both '-' FROM regexp_replace(lower(btrim(article_title)), '[^a-z0-9]+', '-', 'g')),
        160
    ), ''), 'article') || '-' || article_id::text;
$$;

CREATE OR REPLACE FUNCTION require_batch_publication_theme()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    -- A stable identity is batch-only only when it has an immutable batch
    -- revision.  This prevents a public snapshot from becoming a new path to
    -- the retired incremental taxonomy or an orphaned identity.
    IF NOT EXISTS (
        SELECT 1 FROM theme_revisions WHERE theme_id = NEW.stable_theme_id
    ) THEN
        RAISE EXCEPTION 'public publication theme must be a batch theme identity';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER article_publication_themes_batch_only
BEFORE INSERT OR UPDATE ON article_publication_themes
FOR EACH ROW EXECUTE FUNCTION require_batch_publication_theme();

CREATE OR REPLACE FUNCTION reject_article_publication_snapshot_mutation()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'article publication snapshots are immutable';
END;
$$;

CREATE TRIGGER article_publication_themes_immutable
BEFORE UPDATE OR DELETE ON article_publication_themes
FOR EACH ROW EXECUTE FUNCTION reject_article_publication_snapshot_mutation();

-- Backfill only rows that are already approved and wholly associated with
-- migrated stable identities.  A legacy-only association is not public data
-- and is intentionally not copied into this projection.
INSERT INTO article_publications (
    article_id, approved_revision_id, slug, first_published_at, updated_at
)
SELECT
    articles.id,
    articles.current_revision_id,
    public_article_slug(revisions.title, articles.id),
    articles.approved_at,
    articles.updated_at
FROM articles
JOIN article_revisions AS revisions
  ON revisions.id = articles.current_revision_id
WHERE articles.status = 'approved'
  AND articles.approved_at IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM article_themes AS links
      WHERE links.article_id = articles.id
        AND links.stable_theme_id IS NULL
  );

INSERT INTO article_publication_themes(article_id, approved_revision_id, stable_theme_id, display_name)
SELECT publications.article_id, publications.approved_revision_id,
       links.stable_theme_id, links.theme_name_snapshot
FROM article_publications AS publications
JOIN article_themes AS links ON links.article_id = publications.article_id
WHERE links.stable_theme_id IS NOT NULL;

COMMIT;
