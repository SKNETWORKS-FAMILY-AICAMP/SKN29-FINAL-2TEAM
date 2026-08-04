-- EmbeddingGemma emits 768-dimensional vectors. Existing vectors cannot be
-- converted safely from another model, so refuse the migration when data exists.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM vec_idx) THEN
        RAISE EXCEPTION
            'vec_idx must be empty before changing embedding dimensions to 768';
    END IF;
END $$;

ALTER TABLE vec_idx
    ALTER COLUMN embedding TYPE VECTOR(768);
