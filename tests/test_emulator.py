"""Unit and integration tests for the VFS shell emulator."""

import os
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.emulator import ShellProcessor, VirtualFileSystem, parse_cli_args


def build_sample_zip(target_path):
    """Create a 3-level nested ZIP archive for VFS testing."""
    with zipfile.ZipFile(target_path, "w") as zf:
        zf.writestr("readme.txt", "Welcome to VFS\n")
        zf.writestr("docs/guide.txt", "User manual\n")
        zf.writestr("docs/nested/deep.log", "Deep log entry\n")


class TestVirtualFileSystem(unittest.TestCase):
    """Test cases for in-memory ZIP VFS operations and shell commands."""

    def setUp(self):
        """Prepare temporary 3-level ZIP VFS and shell processor."""
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.zip_path = os.path.join(self.tmp_dir.name, "sample.zip")
        build_sample_zip(self.zip_path)
        self.vfs = VirtualFileSystem(self.zip_path)
        self.exited = False
        self.shell = ShellProcessor(self.vfs, self._mark_exit)

    def tearDown(self):
        """Clean up temporary files."""
        self.tmp_dir.cleanup()

    def _mark_exit(self):
        """Callback flag for exit command."""
        self.exited = True

    def test_initial_state_and_pwd(self):
        """Verify VFS name and root working directory."""
        self.assertEqual(self.vfs.name, "sample")
        self.assertEqual(self.shell.execute("pwd"), "/")

    def test_ls_and_cd_navigation(self):
        """Verify directory listing and relative/parent navigation."""
        self.assertEqual(self.shell.execute("ls"), "docs/\nreadme.txt")
        self.shell.execute("cd docs/nested")
        self.assertEqual(self.shell.execute("pwd"), "/docs/nested")
        self.assertEqual(self.shell.execute("ls"), "deep.log")
        self.shell.execute("cd ../..")
        self.assertEqual(self.shell.execute("pwd"), "/")

    def test_find_command(self):
        """Verify recursive search by path and substring."""
        found = self.shell.execute("find / deep")
        self.assertEqual(found, "/docs/nested/deep.log")

    def test_rm_file_and_empty_dir(self):
        """Verify in-memory deletion of files and empty directories."""
        with self.assertRaises(OSError):
            self.shell.execute("rm docs/nested")
        self.shell.execute("rm docs/nested/deep.log")
        self.shell.execute("rm docs/nested")
        self.assertEqual(self.shell.execute("ls docs"), "guide.txt")

    def test_help_and_exit(self):
        """Verify help output and exit callback execution."""
        help_text = self.shell.execute("help")
        self.assertIn("Available commands:", help_text)
        self.shell.execute("exit")
        self.assertTrue(self.exited)

    def test_error_handling_and_cli_args(self):
        """Verify errors on invalid commands/files and CLI parsing."""
        with self.assertRaises(ValueError):
            self.shell.execute("unknown_cmd")
        with self.assertRaises(FileNotFoundError):
            VirtualFileSystem("non_existent_file.zip")
        args = parse_cli_args(["--vfs", "a.zip", "--script", "start.txt"])
        self.assertEqual(args.vfs_path, "a.zip")
        self.assertEqual(args.script_path, "start.txt")


if __name__ == "__main__":
    unittest.main()
