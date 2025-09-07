# Database Migrations Guide

This project uses Alembic for database schema migrations with SQLModel.

## Quick Start

### For New Setups (No existing database)
```bash
# Just run the app - it will create tables automatically
make dev
```

### For Existing Databases
```bash
# Check current migration status
make db-current

# Apply pending migrations
make db-upgrade

# View migration history
make db-history
```

## Migration Commands

### Basic Operations
```bash
# Create new migration (auto-detect changes)
make db-create-migration MESSAGE="Add new field"

# Apply all pending migrations
make db-upgrade

# Check current database version
make db-current

# View migration history
make db-history
```

### Advanced Operations
```bash
# Downgrade to specific revision
make db-downgrade REVISION=abc123

# Mark database as up-to-date without running migrations
make db-stamp
```

## For Your Current Situation

You have existing tables from previous development. Here's how to handle the transition:

### Option 1: Fresh Start (Development Only)
```bash
# Drop your development database and recreate
# This will lose all data but give you a clean start
dropdb your_database_name
createdb your_database_name

# Run the app - tables will be created automatically
make dev
```

### Option 2: Migrate Existing Database
```bash
# First, mark your database as being at the latest migration
# This tells Alembic your database is already up-to-date
make db-stamp

# Check status
make db-current

# From now on, use normal migration workflow
make db-create-migration MESSAGE="Add new feature"
make db-upgrade
```

## Migration Workflow

1. **Make changes** to your SQLModel models in `app/models/`
2. **Create migration** with `make db-create-migration MESSAGE="Description"`
3. **Review migration** file in `alembic/versions/`
4. **Apply migration** with `make db-upgrade`
5. **Commit** both your model changes and migration file

## Important Notes

- Always review generated migrations before applying
- Test migrations on development data first
- Back up production data before running migrations
- Migration files should be committed to version control
- Never edit applied migration files

## Current Migration

The current migration (`229f6d8282e9`) does two things:
1. **Removes complex Chatwoot tables** (chatwoot_profiles, chatwoot_user_contexts, etc.)
2. **Adds phone field** to the user table with unique constraint

If you had data in the removed tables, you may want to export it before applying this migration.

## Troubleshooting

### "Table already exists" errors
```bash
# Mark database as current without running migrations
make db-stamp
```

### "Column already exists" errors
```bash
# Check what Alembic thinks is the current state
make db-current
alembic check
```

### Starting fresh
```bash
# Remove all migration files (keep directory structure)
rm alembic/versions/*.py

# Create new initial migration
make db-create-migration MESSAGE="Initial schema"
```