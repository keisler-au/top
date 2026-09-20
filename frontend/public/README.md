# Public web edge

This dependency-free nginx service is the default internet-facing web edge.
It exposes only `/`, `/insights`, `/insights/{slug}`, `/themes`,
`/themes/{id}-{slug}`, `/about`, `/robots.txt`, `/sitemap.xml`, health, and
self-hosted assets. Every other path is a generic `404`, including all API,
admin, and internal-renderer paths.

Start it with `docker compose up --build`; set `PUBLIC_PORT` to change its host
port. The administrative dashboard is separate: `docker compose --profile
admin up --build` binds `admin-web` only to loopback.

Configure `PUBLIC_SITE_ORIGIN` as an absolute HTTP(S) origin without a path,
query, fragment, or credentials. `PUBLIC_SITE_NAME` and optional
`PUBLIC_SITE_DESCRIPTION` supply public metadata. HTML, robots, and sitemap
responses use a short shared cache lifetime; only content-hashed assets are
immutable. The edge permits no scripts or third-party connections and sends
`nosniff`, restrictive referrer/permissions policies, and frame denial.

The edge renders only approved public-projection revisions. Returning an
article to draft or archiving it withdraws its URL; reapproval keeps the URL
and selects a new immutable projection snapshot. Batch taxonomy lineage
changes never rewrite theme labels in an already approved snapshot.
