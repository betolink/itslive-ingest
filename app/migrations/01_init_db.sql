INSERT INTO pgstac_settings (name, value)
VALUES
    ('default-filter-lang', 'cql-json'),
ON CONFLICT ON CONSTRAINT pgstac_settings_pkey DO UPDATE SET value = excluded.value;
UPDATE collections set partition_trunc='year' where id='itslive-granules';

