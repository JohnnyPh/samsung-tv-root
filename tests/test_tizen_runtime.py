from __future__ import annotations

import tarfile

import pytest

from samsung_tv_root.archive_root import (
    ArchiveRootError,
    _discover_runtime,
    _prepare_artifacts,
)
from samsung_tv_root.sdb import CaptureResult


TIZEN_HELP = (
    "Unknown option --list-runtimes.\n"
    "--clr-path <path> path to libcoreclr.so and runtime assemblies\n"
    "[exit:255]\n"
)


class Client:
    def __init__(self, response=TIZEN_HELP, directories=""):
        self.response = response
        self.directories = directories
        self.commands = []

    def capture(self, command, timeout=15):
        self.commands.append(command)
        output = (
            self.response if "--list-runtimes" in command
            else self.directories + "\n[exit:0]\n"
        )
        return CaptureResult(output, 1)


@pytest.mark.parametrize(
    ("versions", "expected", "selected"),
    [
        (["3.1.3", "6.0.9", "6.0.10", "6.0.0"], "6.0", "6.0.10"),
        (["2.1.4", "3.1.3"], "3.1", "3.1.3"),
    ],
)
def test_tizen_host_selects_verified_runtime_numerically(versions, expected, selected):
    base = "/usr/share/dotnet/shared/Microsoft.NETCore.App/"
    client = Client(directories="\n".join(base + v for v in versions))
    assert _discover_runtime(client) == (expected, base + selected)
    assert 'test -f "$p/libcoreclr.so"' in client.commands[1]
    assert 'test -f "$p/System.Private.CoreLib.dll"' in client.commands[1]


@pytest.mark.parametrize("directories", ["", "/usr/share/dotnet/shared/Microsoft.NETCore.App/2.1.4", "/tmp/6.0.9"])
def test_tizen_host_rejects_missing_unsupported_or_untrusted_runtime(directories):
    with pytest.raises(ArchiveRootError, match="no supported"):
        _discover_runtime(Client(directories=directories))


def test_runtime_discovery_preserves_unrelated_host_failures():
    client = Client(response="Permission denied\n[exit:1]\n")
    with pytest.raises(ArchiveRootError, match="Permission denied"):
        _discover_runtime(client)
    assert len(client.commands) == 1


def test_tizen_clr_path_is_used_in_root_agent_launch(tmp_path, monkeypatch):
    monkeypatch.setattr("samsung_tv_root.archive_root._openssl", lambda *args: None)
    package = "archive-root-0123456789abcdef"
    clr = "/usr/share/dotnet/shared/Microsoft.NETCore.App/6.0.9"
    _prepare_artifacts(tmp_path, "6.0", package, "192.0.2.1", 12345, b"x" * 32, clr)
    with tarfile.open(tmp_path / f"{package}.tar.gz") as archive:
        script = archive.extractfile("launch.sh").read().decode("ascii")
    assert f"exec /usr/bin/dotnet --clr-path {clr} " in script
    assert f"{package}/SamsungTvRootAgent.dll" in script
