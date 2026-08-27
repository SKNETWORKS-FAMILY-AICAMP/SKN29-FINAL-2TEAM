BEGIN;

ALTER TABLE skill_registration_job
    ADD COLUMN IF NOT EXISTS runtime_profile_version VARCHAR(128),
    ADD COLUMN IF NOT EXISTS tool_registry_version VARCHAR(128);

COMMIT;
