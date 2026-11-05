-- Example queries for Postgres.

-- 1. All findings from Retail.ru for the last week (two links: finding -> material -> source)
SELECT m.published_at, f.event_type, f.companies, f.markets, f.region, f.summary, m.url
FROM findings f
JOIN materials m ON m.id = f.material_id
JOIN sources s ON s.id = m.source_id
WHERE s.name = 'Retail.ru' AND m.published_at > now() - interval '7 days'
ORDER BY m.published_at DESC;

-- 2. Runs of every block, newest first
SELECT id, service, status, items, note, started_at, finished_at
FROM runs ORDER BY id DESC LIMIT 20;
