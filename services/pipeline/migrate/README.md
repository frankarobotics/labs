# Migrate

Database migration service for initializing and managing database schemas for episode and task metadata in the data-collection system.

## Overview

Migrate manages PostgreSQL database schema migrations for the data-collection platform, built with
Go 1.21+ and golang-migrate. It ensures that database schemas are versioned, consistent, and
up-to-date across all environments through automated SQL migration files.

### Runtime Responsibilities

1. **Automatic migration execution**: On startup, checks current schema version and applies pending
   migrations sequentially.
2. **Version tracking**: Maintains migration history in the database to prevent duplicate execution.
3. **Rollback support**: Provides safe down-migrations to revert schema changes when needed.
4. **Health monitoring**: Validates database connectivity with retry logic before applying
   migrations.
5. **One-shot execution**: Runs as a one-time job on container startup, then exits.

### Architecture

- **Migration Runner** (`main.go`): CLI application with up/down/goto commands for flexible
  migration control.
- **Custom Logger** (`main.go`): Enhanced logging with filename mapping and status tracking for each
  migration step.
- **Database Manager** (`main.go`): Connection handling with retry logic and health checks for
  PostgreSQL.
- **File System Scanner** (`main.go`): Automatic migration discovery with version mapping from
  `migrations/` directory.

### Configuration

- `DATABASE_URL`: PostgreSQL connection string (format:
  `postgres://user:password@host:port/dbname?sslmode=disable`)
