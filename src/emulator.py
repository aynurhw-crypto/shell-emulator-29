"""UNIX-like OS shell emulator with in-memory ZIP VFS and Tkinter GUI."""

import argparse
import io
import os
import sys
import tkinter as tk
from tkinter import scrolledtext
import zipfile


class VirtualFileSystem:
    """In-memory virtual file system loaded from a ZIP archive."""

    def __init__(self, zip_path=None):
        """Initialize VFS from ZIP file or create a default empty VFS."""
        self.name = "default_vfs"
        self.files = {}
        self.dirs = {"/"}
        self.cwd = "/"
        if zip_path:
            self.load_zip(zip_path)

    def load_zip(self, zip_path):
        """Load directory structure and file bytes into memory."""
        if not os.path.isfile(zip_path):
            raise FileNotFoundError(f"VFS file not found: {zip_path}")
        if not zipfile.is_zipfile(zip_path):
            raise ValueError(f"Invalid ZIP format: {zip_path}")
        self.name = os.path.splitext(os.path.basename(zip_path))[0]
        self.files.clear()
        self.dirs = {"/"}
        with zipfile.ZipFile(zip_path, "r") as archive:
            for item in archive.infolist():
                self._register_entry(archive, item)

    def _register_entry(self, archive, item):
        """Register a single ZIP entry into virtual directories or files."""
        clean = "/" + item.filename.strip("/")
        if clean == "/":
            return
        self._ensure_parents(clean)
        if item.is_dir():
            self.dirs.add(clean)
        else:
            self.files[clean] = archive.read(item.filename)

    def _ensure_parents(self, path):
        """Ensure all parent directories exist for a given virtual path."""
        parts = path.strip("/").split("/")
        current = ""
        for part in parts[:-1]:
            current += "/" + part
            self.dirs.add(current)

    def resolve_path(self, target):
        """Resolve relative or absolute path inside VFS."""
        if not target or target == ".":
            return self.cwd
        raw = target if target.startswith("/") else f"{self.cwd}/{target}"
        stack = []
        for part in raw.split("/"):
            if part in ("", "."):
                continue
            if part == "..":
                if stack:
                    stack.pop()
            else:
                stack.append(part)
        return "/" + "/".join(stack)

    def list_dir(self, target=None):
        """Return sorted entries inside the target directory."""
        path = self.resolve_path(target)
        if path not in self.dirs:
            raise FileNotFoundError(f"ls: cannot access '{target}': No dir")
        prefix = "/" if path == "/" else path + "/"
        entries = set()
        for d_path in self.dirs:
            if d_path.startswith(prefix) and d_path != path:
                rest = d_path[len(prefix):].split("/")[0]
                entries.add(rest + "/")
        for f_path in self.files:
            if f_path.startswith(prefix):
                rest = f_path[len(prefix):]
                if "/" not in rest:
                    entries.add(rest)
        return sorted(entries)

    def change_dir(self, target):
        """Change current working directory in VFS."""
        path = self.resolve_path(target)
        if path not in self.dirs:
            raise FileNotFoundError(f"cd: {target}: No such directory")
        self.cwd = path

    def find_entries(self, start_path, name_query=None):
        """Find all files and directories under start_path matching query."""
        base = self.resolve_path(start_path)
        if base not in self.dirs and base not in self.files:
            raise FileNotFoundError(f"find: '{start_path}': No such path")
        results = []
        all_nodes = sorted(self.dirs | set(self.files.keys()))
        for node in all_nodes:
            if node == base or node.startswith(base.rstrip("/") + "/"):
                node_name = "/" if node == "/" else node.rsplit("/", 1)[-1]
                if not name_query or name_query in node_name:
                    results.append(node)
        return results

    def remove_entry(self, target):
        """Remove a file or empty directory from memory."""
        path = self.resolve_path(target)
        if path == "/":
            raise PermissionError("rm: cannot remove root directory")
        if path in self.files:
            del self.files[path]
            return
        if path in self.dirs:
            if self.list_dir(path):
                raise OSError(f"rm: cannot remove '{target}': Not empty")
            self.dirs.remove(path)
            return
        raise FileNotFoundError(f"rm: cannot remove '{target}': Not found")


class ShellProcessor:
    """Command parser and executor for the VFS shell."""

    def __init__(self, vfs, exit_callback):
        """Bind VFS instance and exit callback."""
        self.vfs = vfs
        self.exit_callback = exit_callback
        self.commands = {
            "ls": self._cmd_ls,
            "cd": self._cmd_cd,
            "pwd": self._cmd_pwd,
            "find": self._cmd_find,
            "rm": self._cmd_rm,
            "help": self._cmd_help,
            "exit": self._cmd_exit,
        }

    def execute(self, line):
        """Parse command line by spaces and run matching handler."""
        tokens = line.strip().split()
        if not tokens:
            return ""
        cmd, args = tokens[0], tokens[1:]
        handler = self.commands.get(cmd)
        if not handler:
            raise ValueError(f"{cmd}: command not found")
        return handler(args)

    def _cmd_ls(self, args):
        """Handle ls command."""
        if len(args) > 1:
            raise ValueError("ls: too many arguments")
        target = args[0] if args else None
        return "\n".join(self.vfs.list_dir(target))

    def _cmd_cd(self, args):
        """Handle cd command."""
        if len(args) != 1:
            raise ValueError("cd: expected exactly 1 argument")
        self.vfs.change_dir(args[0])
        return ""

    def _cmd_pwd(self, args):
        """Handle pwd command."""
        if args:
            raise ValueError("pwd: too many arguments")
        return self.vfs.cwd

    def _cmd_find(self, args):
        """Handle find command."""
        if not args or len(args) > 2:
            raise ValueError("find: usage: find <path> [name]")
        query = args[1] if len(args) == 2 else None
        return "\n".join(self.vfs.find_entries(args[0], query))

    def _cmd_rm(self, args):
        """Handle rm command."""
        if len(args) != 1:
            raise ValueError("rm: expected exactly 1 argument")
        self.vfs.remove_entry(args[0])
        return ""

    def _cmd_help(self, args):
        """Handle help command."""
        if args:
            raise ValueError("help: too many arguments")
        return (
            "Available commands:\n"
            "  ls [path]         - list directory contents\n"
            "  cd <path>         - change current directory\n"
            "  pwd               - print working directory\n"
            "  find <path> [str] - search files and directories\n"
            "  rm <path>         - remove file or empty directory\n"
            "  help              - show this help message\n"
            "  exit              - close the emulator"
        )

    def _cmd_exit(self, args):
        """Handle exit command."""
        if args:
            raise ValueError("exit: too many arguments")
        self.exit_callback()
        return ""


class EmulatorGUI:
    """Tkinter graphical terminal interface."""

    def __init__(self, vfs_path=None, script_path=None):
        """Set up GUI window, debug startup output, and startup script."""
        self.root = tk.Tk()
        self.vfs = VirtualFileSystem()
        self.shell = ShellProcessor(self.vfs, self.root.destroy)
        self._build_widgets()
        self._log(f"[DEBUG] vfs_path={vfs_path}, script_path={script_path}")
        self._init_vfs(vfs_path)
        self.root.title(f"VFS Emulator - {self.vfs.name}")
        if script_path:
            self._run_script(script_path)

    def _build_widgets(self):
        """Create terminal output area and command input bar."""
        self.output = scrolledtext.ScrolledText(
            self.root, wrap=tk.WORD, width=80, height=24, state=tk.DISABLED
        )
        self.output.pack(padx=8, pady=8, fill=tk.BOTH, expand=True)
        self.entry = tk.Entry(self.root)
        self.entry.pack(padx=8, pady=(0, 8), fill=tk.X)
        self.entry.bind("<Return>", self._on_enter)
        self.entry.focus_set()

    def _init_vfs(self, vfs_path):
        """Load VFS if provided and report any load errors."""
        if not vfs_path:
            return
        try:
            self.vfs.load_zip(vfs_path)
        except Exception as exc:
            self._log(f"[ERROR] VFS load failed: {exc}")

    def _prompt(self):
        """Return UNIX-like shell prompt string."""
        return f"{self.vfs.name}:{self.vfs.cwd}$ "

    def _log(self, text):
        """Append line to terminal output widget."""
        if not text:
            return
        self.output.configure(state=tk.NORMAL)
        self.output.insert(tk.END, text + "\n")
        self.output.see(tk.END)
        self.output.configure(state=tk.DISABLED)

    def _on_enter(self, _event=None):
        """Handle interactive command submission."""
        line = self.entry.get()
        self.entry.delete(0, tk.END)
        self._process_line(line)

    def _process_line(self, line):
        """Display prompt with command, run it, and print output or error."""
        self._log(f"{self._prompt()}{line}")
        try:
            result = self.shell.execute(line)
            self._log(result)
        except Exception as exc:
            self._log(f"Error: {exc}")

    def _run_script(self, script_path):
        """Execute startup script line by line, skipping errors."""
        if not os.path.isfile(script_path):
            self._log(f"[ERROR] Script not found: {script_path}")
            return
        with open(script_path, "r", encoding="utf-8") as handle:
            for raw_line in handle:
                clean = raw_line.strip()
                if clean:
                    self._process_line(clean)

    def run(self):
        """Start the Tkinter main event loop."""
        self.root.mainloop()


def parse_cli_args(argv=None):
    """Parse command-line parameters for VFS path and startup script."""
    parser = argparse.ArgumentParser(description="OS Shell Emulator")
    parser.add_argument("--vfs", dest="vfs_path", help="Path to VFS ZIP")
    parser.add_argument("--script", dest="script_path", help="Startup script")
    return parser.parse_args(argv)


def main():
    """Entry point for starting the emulator GUI."""
    args = parse_cli_args()
    app = EmulatorGUI(vfs_path=args.vfs_path, script_path=args.script_path)
    app.run()


if __name__ == "__main__":
    main()
