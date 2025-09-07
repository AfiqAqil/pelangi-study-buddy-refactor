#!/usr/bin/env python3
"""Database migration management script."""

import sys
import subprocess
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def run_command(command: list[str]) -> int:
    """Run a command and return exit code."""
    try:
        result = subprocess.run(command, check=False)
        return result.returncode
    except FileNotFoundError:
        print(f"Error: Command not found: {command[0]}")
        return 1

def create_migration(message: str = None) -> int:
    """Create a new migration."""
    cmd = ["uv", "run", "alembic", "revision", "--autogenerate"]
    if message:
        cmd.extend(["-m", message])
    else:
        cmd.extend(["-m", "Auto-generated migration"])
    
    print(f"Creating migration: {' '.join(cmd)}")
    return run_command(cmd)

def upgrade_db(revision: str = "head") -> int:
    """Upgrade database to specified revision."""
    cmd = ["uv", "run", "alembic", "upgrade", revision]
    print(f"Upgrading database: {' '.join(cmd)}")
    return run_command(cmd)

def downgrade_db(revision: str) -> int:
    """Downgrade database to specified revision."""
    cmd = ["uv", "run", "alembic", "downgrade", revision]
    print(f"Downgrading database: {' '.join(cmd)}")
    return run_command(cmd)

def show_history() -> int:
    """Show migration history."""
    cmd = ["uv", "run", "alembic", "history", "--verbose"]
    print("Migration history:")
    return run_command(cmd)

def show_current() -> int:
    """Show current revision."""
    cmd = ["uv", "run", "alembic", "current", "--verbose"]
    print("Current revision:")
    return run_command(cmd)

def stamp_db(revision: str = "head") -> int:
    """Stamp database with revision without running migrations."""
    cmd = ["uv", "run", "alembic", "stamp", revision]
    print(f"Stamping database: {' '.join(cmd)}")
    return run_command(cmd)

def main():
    """Main CLI interface."""
    if len(sys.argv) < 2:
        print("""
Database Migration Manager

Usage:
    python scripts/db_migrate.py <command> [args]

Commands:
    create [message]    - Create a new migration (auto-generate)
    upgrade [revision]  - Upgrade to revision (default: head)
    downgrade revision  - Downgrade to revision
    history            - Show migration history
    current            - Show current revision
    stamp [revision]   - Mark database as up to date without running migrations

Examples:
    python scripts/db_migrate.py create "Add phone field to user"
    python scripts/db_migrate.py upgrade
    python scripts/db_migrate.py history
    python scripts/db_migrate.py current
    python scripts/db_migrate.py stamp head  # Mark existing DB as current
        """)
        return 1

    command = sys.argv[1].lower()
    
    if command == "create":
        message = sys.argv[2] if len(sys.argv) > 2 else None
        return create_migration(message)
    
    elif command == "upgrade":
        revision = sys.argv[2] if len(sys.argv) > 2 else "head"
        return upgrade_db(revision)
    
    elif command == "downgrade":
        if len(sys.argv) < 3:
            print("Error: downgrade requires revision argument")
            return 1
        return downgrade_db(sys.argv[2])
    
    elif command == "history":
        return show_history()
    
    elif command == "current":
        return show_current()
    
    elif command == "stamp":
        revision = sys.argv[2] if len(sys.argv) > 2 else "head"
        return stamp_db(revision)
    
    else:
        print(f"Error: Unknown command '{command}'")
        return 1

if __name__ == "__main__":
    sys.exit(main())