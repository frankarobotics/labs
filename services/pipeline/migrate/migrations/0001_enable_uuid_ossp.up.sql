-- Enable the "uuid-ossp" extension for UUID generation
-- This provides uuid_generate_v4() function for random UUIDs
-- Note: PostgreSQL 18+ has built-in uuid_generate_v7() for time-ordered UUIDs
-- which provide better performance for primary keys due to improved locality
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
