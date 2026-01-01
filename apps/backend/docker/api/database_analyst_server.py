"""
Database Analyst Container Server
==================================

FastAPI server for the Database Analyst container.
Analyzes database schema and data requirements before coding begins.
"""

import os
import logging
import subprocess
from typing import Optional

from .base_server import (
    BaseContainerServer,
    StartRequest,
    TaskStatus,
    create_start_endpoint,
    safe_format_prompt,
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DatabaseAnalystServer(BaseContainerServer):
    """
    Database Analyst container server.

    Analyzes database schema using psql/mysql CLI commands
    and generates context for subsequent workflow steps.
    """

    def __init__(self):
        super().__init__(name="Database Analyst", port=None)
        create_start_endpoint(self)

    def _get_postgres_config(self) -> Optional[dict[str, str]]:
        """
        Get PostgreSQL connection configuration from environment.

        Returns:
            Dictionary with connection parameters or None if not configured
        """
        host = os.environ.get("PGHOST")
        port = os.environ.get("PGPORT", "5432")
        user = os.environ.get("PGUSER")
        password = os.environ.get("PGPASSWORD")
        database = os.environ.get("PGDATABASE")

        if not all([host, user, password, database]):
            return None

        return {
            "host": host,
            "port": port,
            "user": user,
            "password": password,
            "database": database,
        }

    def _get_mysql_config(self) -> Optional[dict[str, str]]:
        """
        Get MySQL connection configuration from environment.

        Returns:
            Dictionary with connection parameters or None if not configured
        """
        host = os.environ.get("MYSQL_HOST")
        port = os.environ.get("MYSQL_PORT", "3306")
        user = os.environ.get("MYSQL_USER")
        password = os.environ.get("MYSQL_PASSWORD")
        database = os.environ.get("MYSQL_DATABASE")

        if not all([host, user, password, database]):
            return None

        return {
            "host": host,
            "port": port,
            "user": user,
            "password": password,
            "database": database,
        }

    def _execute_psql(
        self, config: dict[str, str], query: str, timeout: int = 30
    ) -> tuple[bool, str]:
        """
        Execute a PostgreSQL query using psql CLI.

        Args:
            config: Database connection configuration
            query: SQL query to execute
            timeout: Command timeout in seconds

        Returns:
            Tuple of (success, output)
        """
        env = os.environ.copy()
        env["PGPASSWORD"] = config["password"]

        cmd = [
            "psql",
            "-h",
            config["host"],
            "-p",
            config["port"],
            "-U",
            config["user"],
            "-d",
            config["database"],
            "-c",
            query,
            "--no-password",
            "-t",  # Tuples only (no headers)
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
            )
            if result.returncode == 0:
                return True, result.stdout
            else:
                return False, result.stderr
        except subprocess.TimeoutExpired:
            return False, "Query timed out"
        except FileNotFoundError:
            return False, "psql client not found"
        except Exception as e:
            return False, str(e)

    def _execute_mysql(
        self, config: dict[str, str], query: str, timeout: int = 30
    ) -> tuple[bool, str]:
        """
        Execute a MySQL query using mysql CLI.

        Args:
            config: Database connection configuration
            query: SQL query to execute
            timeout: Command timeout in seconds

        Returns:
            Tuple of (success, output)
        """
        cmd = [
            "mysql",
            "-h",
            config["host"],
            "-P",
            config["port"],
            "-u",
            config["user"],
            f"-p{config['password']}",
            config["database"],
            "-e",
            query,
            "-N",  # Skip column names
            "-B",  # Batch mode (tab-separated)
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            if result.returncode == 0:
                return True, result.stdout
            else:
                return False, result.stderr
        except subprocess.TimeoutExpired:
            return False, "Query timed out"
        except FileNotFoundError:
            return False, "mysql client not found"
        except Exception as e:
            return False, str(e)

    def _get_postgres_schema(self, config: dict[str, str]) -> str:
        """
        Get PostgreSQL schema information.

        Args:
            config: Database connection configuration

        Returns:
            Schema information as formatted text
        """
        schema_parts = []

        # Get list of tables
        self.update_status(TaskStatus.RUNNING, "Fetching table list", progress=10)
        success, tables = self._execute_psql(
            config,
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name;
            """,
        )

        if not success:
            return f"Error fetching tables: {tables}"

        table_list = [t.strip() for t in tables.strip().split("\n") if t.strip()]

        if not table_list:
            return "No tables found in the database."

        # Limit to first 50 tables for large schemas
        if len(table_list) > 50:
            schema_parts.append(
                f"Note: Found {len(table_list)} tables. Showing first 50."
            )
            table_list = table_list[:50]

        schema_parts.append(f"Tables ({len(table_list)}):")
        schema_parts.append("-" * 40)

        # Get column information for each table
        progress_per_table = 70 / len(table_list)
        for i, table in enumerate(table_list):
            self.update_status(
                TaskStatus.RUNNING,
                f"Analyzing table: {table}",
                progress=int(10 + (i * progress_per_table)),
            )

            success, columns = self._execute_psql(
                config,
                f"""
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = '{table}'
                ORDER BY ordinal_position;
                """,
            )

            schema_parts.append(f"\n{table}:")
            if success:
                for line in columns.strip().split("\n"):
                    if line.strip():
                        parts = [p.strip() for p in line.split("|")]
                        if len(parts) >= 2:
                            col_name = parts[0]
                            col_type = parts[1]
                            nullable = parts[2] if len(parts) > 2 else "YES"
                            default = parts[3] if len(parts) > 3 else ""
                            null_marker = "" if nullable == "YES" else " NOT NULL"
                            default_marker = f" DEFAULT {default}" if default else ""
                            schema_parts.append(
                                f"  - {col_name}: {col_type}{null_marker}{default_marker}"
                            )
            else:
                schema_parts.append(f"  Error: {columns}")

        # Get foreign key relationships
        self.update_status(
            TaskStatus.RUNNING, "Fetching foreign key relationships", progress=80
        )
        success, fk_info = self._execute_psql(
            config,
            """
            SELECT
                tc.table_name,
                kcu.column_name,
                ccu.table_name AS foreign_table,
                ccu.column_name AS foreign_column
            FROM information_schema.table_constraints AS tc
            JOIN information_schema.key_column_usage AS kcu
                ON tc.constraint_name = kcu.constraint_name
            JOIN information_schema.constraint_column_usage AS ccu
                ON ccu.constraint_name = tc.constraint_name
            WHERE tc.constraint_type = 'FOREIGN KEY'
            ORDER BY tc.table_name;
            """,
        )

        if success and fk_info.strip():
            schema_parts.append("\nForeign Key Relationships:")
            schema_parts.append("-" * 40)
            for line in fk_info.strip().split("\n"):
                if line.strip():
                    parts = [p.strip() for p in line.split("|")]
                    if len(parts) >= 4:
                        schema_parts.append(
                            f"  {parts[0]}.{parts[1]} -> {parts[2]}.{parts[3]}"
                        )

        # Get indexes
        self.update_status(TaskStatus.RUNNING, "Fetching indexes", progress=90)
        success, indexes = self._execute_psql(
            config,
            """
            SELECT
                tablename,
                indexname,
                indexdef
            FROM pg_indexes
            WHERE schemaname = 'public'
            ORDER BY tablename, indexname
            LIMIT 100;
            """,
        )

        if success and indexes.strip():
            schema_parts.append("\nIndexes (first 100):")
            schema_parts.append("-" * 40)
            for line in indexes.strip().split("\n"):
                if line.strip():
                    parts = [p.strip() for p in line.split("|")]
                    if len(parts) >= 2:
                        schema_parts.append(f"  {parts[0]}: {parts[1]}")

        return "\n".join(schema_parts)

    def _get_mysql_schema(self, config: dict[str, str]) -> str:
        """
        Get MySQL schema information.

        Args:
            config: Database connection configuration

        Returns:
            Schema information as formatted text
        """
        schema_parts = []

        # Get list of tables
        self.update_status(TaskStatus.RUNNING, "Fetching table list", progress=10)
        success, tables = self._execute_mysql(config, "SHOW TABLES;")

        if not success:
            return f"Error fetching tables: {tables}"

        table_list = [t.strip() for t in tables.strip().split("\n") if t.strip()]

        if not table_list:
            return "No tables found in the database."

        # Limit to first 50 tables for large schemas
        if len(table_list) > 50:
            schema_parts.append(
                f"Note: Found {len(table_list)} tables. Showing first 50."
            )
            table_list = table_list[:50]

        schema_parts.append(f"Tables ({len(table_list)}):")
        schema_parts.append("-" * 40)

        # Get column information for each table
        progress_per_table = 70 / len(table_list)
        for i, table in enumerate(table_list):
            self.update_status(
                TaskStatus.RUNNING,
                f"Analyzing table: {table}",
                progress=int(10 + (i * progress_per_table)),
            )

            success, columns = self._execute_mysql(config, f"DESCRIBE `{table}`;")

            schema_parts.append(f"\n{table}:")
            if success:
                for line in columns.strip().split("\n"):
                    if line.strip():
                        parts = line.split("\t")
                        if len(parts) >= 2:
                            col_name = parts[0]
                            col_type = parts[1]
                            nullable = parts[2] if len(parts) > 2 else "YES"
                            key = parts[3] if len(parts) > 3 else ""
                            default = parts[4] if len(parts) > 4 else ""
                            null_marker = "" if nullable == "YES" else " NOT NULL"
                            key_marker = f" [{key}]" if key else ""
                            default_marker = f" DEFAULT {default}" if default else ""
                            schema_parts.append(
                                f"  - {col_name}: {col_type}{null_marker}{key_marker}{default_marker}"
                            )
            else:
                schema_parts.append(f"  Error: {columns}")

        # Get foreign key relationships
        self.update_status(
            TaskStatus.RUNNING, "Fetching foreign key relationships", progress=80
        )
        success, fk_info = self._execute_mysql(
            config,
            f"""
            SELECT
                TABLE_NAME,
                COLUMN_NAME,
                REFERENCED_TABLE_NAME,
                REFERENCED_COLUMN_NAME
            FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
            WHERE REFERENCED_TABLE_SCHEMA = '{config["database"]}'
            ORDER BY TABLE_NAME;
            """,
        )

        if success and fk_info.strip():
            schema_parts.append("\nForeign Key Relationships:")
            schema_parts.append("-" * 40)
            for line in fk_info.strip().split("\n"):
                if line.strip():
                    parts = line.split("\t")
                    if len(parts) >= 4:
                        schema_parts.append(
                            f"  {parts[0]}.{parts[1]} -> {parts[2]}.{parts[3]}"
                        )

        # Get indexes
        self.update_status(TaskStatus.RUNNING, "Fetching indexes", progress=90)
        success, indexes = self._execute_mysql(
            config,
            f"""
            SELECT
                TABLE_NAME,
                INDEX_NAME,
                COLUMN_NAME
            FROM INFORMATION_SCHEMA.STATISTICS
            WHERE TABLE_SCHEMA = '{config["database"]}'
            ORDER BY TABLE_NAME, INDEX_NAME
            LIMIT 100;
            """,
        )

        if success and indexes.strip():
            schema_parts.append("\nIndexes (first 100):")
            schema_parts.append("-" * 40)
            for line in indexes.strip().split("\n"):
                if line.strip():
                    parts = line.split("\t")
                    if len(parts) >= 3:
                        schema_parts.append(f"  {parts[0]}: {parts[1]} ({parts[2]})")

        return "\n".join(schema_parts)

    async def _run_task(self, request: StartRequest) -> None:
        """
        Execute database analysis task.

        Analyzes database schema using available CLI tools
        and generates context for subsequent workflow steps.

        Args:
            request: The task start request
        """
        logger.info(f"Starting database analysis for spec: {request.spec_id}")

        # Check for database configuration
        pg_config = self._get_postgres_config()
        mysql_config = self._get_mysql_config()

        if not pg_config and not mysql_config:
            logger.warning("No database configured. Skipping analysis.")
            self.update_status(
                TaskStatus.SKIPPED,
                "No database configured. Analysis skipped.",
                progress=100,
            )
            return

        self.update_status(
            TaskStatus.RUNNING,
            "Connecting to database",
            progress=5,
        )

        # Collect schema information
        schema_info = ""
        db_type = ""

        if pg_config:
            db_type = "PostgreSQL"
            logger.info(f"Analyzing PostgreSQL database: {pg_config['database']}")

            # Test connection
            success, result = self._execute_psql(pg_config, "SELECT 1;")
            if not success:
                logger.error(f"Failed to connect to PostgreSQL: {result}")
                self.update_status(
                    TaskStatus.SKIPPED,
                    f"Database connection failed: {result}. Analysis skipped.",
                    progress=100,
                )
                return

            schema_info = self._get_postgres_schema(pg_config)

        elif mysql_config:
            db_type = "MySQL"
            logger.info(f"Analyzing MySQL database: {mysql_config['database']}")

            # Test connection
            success, result = self._execute_mysql(mysql_config, "SELECT 1;")
            if not success:
                logger.error(f"Failed to connect to MySQL: {result}")
                self.update_status(
                    TaskStatus.SKIPPED,
                    f"Database connection failed: {result}. Analysis skipped.",
                    progress=100,
                )
                return

            schema_info = self._get_mysql_schema(mysql_config)

        # Generate analysis summary
        self.update_status(
            TaskStatus.RUNNING,
            "Generating analysis summary",
            progress=95,
        )

        analysis_output = f"""
# Database Analysis Report

## Database Type
{db_type}

## Schema Overview
{schema_info}

## Analysis Notes
- Schema analysis completed successfully
- This context should be used to inform implementation decisions
- Pay attention to foreign key relationships when modifying related tables
- Consider existing indexes when adding queries

## Recommendations
- Review the schema before implementing any database-related changes
- Ensure data types match expected values
- Consider adding migrations for any schema changes
"""

        # Store the analysis output for subsequent steps
        # This would typically be saved to a file or passed to the orchestrator
        output_path = "/workspace/.auto-claude/database_analysis.md"
        try:
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            with open(output_path, "w") as f:
                f.write(analysis_output)
            logger.info(f"Database analysis saved to: {output_path}")
        except Exception as e:
            logger.warning(f"Failed to save analysis output: {e}")

        self.update_status(
            TaskStatus.COMPLETED,
            f"Database analysis completed. Found schema for {db_type}.",
            progress=100,
        )


def main():
    """Entry point for the Database Analyst container."""
    server = DatabaseAnalystServer()
    server.run()


if __name__ == "__main__":
    main()
