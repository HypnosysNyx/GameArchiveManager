"""Focused coverage for the opt-in LZ4 installer offer."""

import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import main
from tools.models import ToolInfo, ToolName
from tools.tool_manager import ToolManager


class Lz4InstallOfferTests(unittest.TestCase):
    def test_verified_lz4_does_not_prompt(self):
        manager = MagicMock()
        manager.get_tool_status.return_value = ToolInfo(
            tool_name=ToolName.LZ4, verified=True
        )
        with patch("builtins.input") as prompt:
            self.assertFalse(main.offer_lz4_install(manager))
        prompt.assert_not_called()
        manager.install_lz4.assert_not_called()

    def test_only_y_starts_download(self):
        manager = MagicMock()
        manager.get_tool_status.return_value = ToolInfo(tool_name=ToolName.LZ4)
        manager.install_lz4.return_value = True
        with patch("builtins.input", return_value="Y"):
            self.assertTrue(main.offer_lz4_install(manager))
        manager.install_lz4.assert_called_once_with()

    def test_other_input_does_not_start_download(self):
        manager = MagicMock()
        manager.get_tool_status.return_value = ToolInfo(tool_name=ToolName.LZ4)
        with patch("builtins.input", return_value=""):
            self.assertFalse(main.offer_lz4_install(manager))
        manager.install_lz4.assert_not_called()

    def test_installer_extracts_only_lz4_exe_from_official_release(self):
        archive_bytes = io.BytesIO()
        with zipfile.ZipFile(archive_bytes, "w") as archive:
            archive.writestr("lz4-1.10.0-win64/lz4.exe", b"official-lz4")

        class Response(io.BytesIO):
            def __init__(self, content, url):
                super().__init__(content)
                self.url = url

            def geturl(self):
                return self.url

            def __enter__(self):
                return self

            def __exit__(self, *unused):
                self.close()

        class Opener:
            def __init__(self):
                self.urls = []

            def open(self, request):
                self.urls.append(request.full_url)
                if request.full_url.endswith("/latest"):
                    return Response(
                        b"release page without asset links",
                        "https://github.com/lz4/lz4/releases/tag/v1.10.0",
                    )
                if "/expanded_assets/" in request.full_url:
                    return Response(
                        b'<a href="/lz4/lz4/releases/download/v1.10.0/lz4_win64_v1_10_0.zip">',
                        request.full_url,
                    )
                return Response(
                    archive_bytes.getvalue(),
                    "https://release-assets.githubusercontent.com/lz4_win64_v1_10_0.zip",
                )

        opener = Opener()
        manager = ToolManager(project_root=Path(tempfile.gettempdir()))
        with tempfile.TemporaryDirectory() as destination:
            install_path = Path(destination) / "LZ4" / "lz4.exe"
            with (
                patch("tools.tool_manager.build_opener", return_value=opener),
                patch.object(manager, "LZ4_INSTALL_PATH", install_path),
                patch.object(manager, "refresh_tool", return_value=True),
            ):
                self.assertTrue(manager.install_lz4())
            self.assertEqual(install_path.read_bytes(), b"official-lz4")
        self.assertEqual(
            opener.urls,
            [
                "https://github.com/lz4/lz4/releases/latest",
                "https://github.com/lz4/lz4/releases/expanded_assets/v1.10.0",
                "https://github.com/lz4/lz4/releases/download/v1.10.0/lz4_win64_v1_10_0.zip",
            ],
        )

    def test_installer_rejects_non_github_release_host_without_writing_file(self):
        class Response(io.BytesIO):
            def __init__(self, content, url):
                super().__init__(content)
                self.url = url

            def geturl(self):
                return self.url

            def __enter__(self):
                return self

            def __exit__(self, *unused):
                self.close()

        class Opener:
            def open(self, request):
                if request.full_url.endswith("/latest"):
                    return Response(
                        b"release page without asset links",
                        "https://github.com/lz4/lz4/releases/tag/v1.10.0",
                    )
                if "/expanded_assets/" in request.full_url:
                    return Response(
                        b'<a href="/lz4/lz4/releases/download/v1.10.0/lz4_win64_v1_10_0.zip">',
                        request.full_url,
                    )
                return Response(
                    b"not-an-archive",
                    "https://example.com/lz4_win64_v1_10_0.zip",
                )

        manager = ToolManager(project_root=Path(tempfile.gettempdir()))
        with tempfile.TemporaryDirectory() as destination:
            install_path = Path(destination) / "LZ4" / "lz4.exe"
            with (
                patch("tools.tool_manager.build_opener", return_value=Opener()),
                patch.object(manager, "LZ4_INSTALL_PATH", install_path),
            ):
                with self.assertRaisesRegex(RuntimeError, "left the official repository"):
                    manager.install_lz4()
            self.assertFalse(install_path.exists())


if __name__ == "__main__":
    unittest.main()
