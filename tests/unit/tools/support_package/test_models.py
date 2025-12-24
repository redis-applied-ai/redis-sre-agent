"""Tests for support package models."""

from pathlib import Path


class TestSupportPackageDatabase:
    """Tests for SupportPackageDatabase model."""

    def test_from_directory_parses_database_files(self, tmp_path: Path):
        """Test parsing database directory with info, slowlog, clientlist files."""
        from redis_sre_agent.tools.support_package.models import SupportPackageDatabase

        # Create a mock database directory
        db_dir = tmp_path / "database_4"
        db_dir.mkdir()

        # Create mock files
        (db_dir / "database_4.info").write_text("# Server\nredis_version:8.4.0\n")
        (db_dir / "database_4.slowlog").write_text("SLOWLOG\n1 2025-11-24T11:42:01+00:00Z 65.325 [b'CLUSTER']\n")
        (db_dir / "database_4.clientlist").write_text("CLIENT LIST\nid=1000 addr=10.0.101.36:58696\n")
        (db_dir / "database_4.rladmin").write_text("DB INFO FOR BDB 4\ndb:4 [test-db-asm]:\n")

        db = SupportPackageDatabase.from_directory(db_dir)

        assert db.database_id == "4"
        assert db.name == "database_4"
        assert db.info_content is not None
        assert "redis_version:8.4.0" in db.info_content
        assert db.slowlog_content is not None
        assert db.clientlist_content is not None
        assert db.rladmin_content is not None

    def test_database_id_extraction(self, tmp_path: Path):
        """Test that database ID is correctly extracted from directory name."""
        from redis_sre_agent.tools.support_package.models import SupportPackageDatabase

        db_dir = tmp_path / "database_123"
        db_dir.mkdir()
        (db_dir / "database_123.info").write_text("# Server\n")

        db = SupportPackageDatabase.from_directory(db_dir)
        assert db.database_id == "123"


class TestSupportPackageNode:
    """Tests for SupportPackageNode model."""

    def test_from_directory_parses_node_files(self, tmp_path: Path):
        """Test parsing node directory with logs and config files."""
        from redis_sre_agent.tools.support_package.models import SupportPackageNode

        # Create a mock node directory
        node_dir = tmp_path / "node_1"
        node_dir.mkdir()
        logs_dir = node_dir / "logs"
        logs_dir.mkdir()

        # Create mock files
        (node_dir / "node_1_sys_info.txt").write_text("System info content")
        (node_dir / "node_1.rladmin").write_text("rladmin status content")
        (logs_dir / "event_log.log").write_text("2025-11-24 10:53:15 INFO EventLog: {}")
        (logs_dir / "dmcproxy.log").write_text("DMC proxy log content")

        node = SupportPackageNode.from_directory(node_dir)

        assert node.node_id == "1"
        assert node.name == "node_1"
        assert node.sys_info_content is not None
        assert "System info content" in node.sys_info_content
        assert len(node.log_files) >= 2


class TestSupportPackage:
    """Tests for SupportPackage model."""

    def test_from_directory_parses_full_package(self, tmp_path: Path):
        """Test parsing a complete support package directory."""
        from redis_sre_agent.tools.support_package.models import SupportPackage

        # Create database directories
        db3_dir = tmp_path / "database_3"
        db3_dir.mkdir()
        (db3_dir / "database_3.info").write_text("# Server\nredis_version:8.4.0\n")

        db4_dir = tmp_path / "database_4"
        db4_dir.mkdir()
        (db4_dir / "database_4.info").write_text("# Server\nredis_version:8.4.0\n")

        # Create node directories
        node1_dir = tmp_path / "node_1"
        node1_dir.mkdir()
        (node1_dir / "logs").mkdir()
        (node1_dir / "node_1_sys_info.txt").write_text("Node 1 info")

        # Create usage report
        (tmp_path / "usage_report.usg").write_text("Usage report content")

        pkg = SupportPackage.from_directory(tmp_path)

        assert len(pkg.databases) == 2
        assert len(pkg.nodes) == 1
        assert pkg.usage_report_content is not None

    def test_get_database_by_id(self, tmp_path: Path):
        """Test retrieving a database by its ID."""
        from redis_sre_agent.tools.support_package.models import SupportPackage

        db_dir = tmp_path / "database_4"
        db_dir.mkdir()
        (db_dir / "database_4.info").write_text("# Server\n")

        pkg = SupportPackage.from_directory(tmp_path)
        db = pkg.get_database("4")

        assert db is not None
        assert db.database_id == "4"

    def test_get_node_by_id(self, tmp_path: Path):
        """Test retrieving a node by its ID."""
        from redis_sre_agent.tools.support_package.models import SupportPackage

        node_dir = tmp_path / "node_2"
        node_dir.mkdir()
        (node_dir / "logs").mkdir()
        (node_dir / "node_2_sys_info.txt").write_text("Node info")

        pkg = SupportPackage.from_directory(tmp_path)
        node = pkg.get_node("2")

        assert node is not None
        assert node.node_id == "2"
