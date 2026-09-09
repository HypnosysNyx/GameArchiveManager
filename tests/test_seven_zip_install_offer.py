"""Consent and installer-selection tests for the optional 7-Zip install."""

import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import Mock, patch

from config.settings import Settings
from main import CliSessionController, offer_seven_zip_install
from tools.models import ToolInfo, ToolName
from tools.tool_manager import ToolManager


def seven_zip_info(*, verified: bool) -> ToolInfo:
    return ToolInfo(
        tool_name=ToolName.SEVEN_ZIP,
        path=Path("C:/missing/7z.exe") if not verified else Path("C:/7z.exe"),
        available=verified,
        verified=verified,
    )


class SevenZipInstallOfferTests(unittest.TestCase):
    def test_verified_seven_zip_is_not_offered(self):
        manager = Mock()
        manager.get_tool_status.return_value = seven_zip_info(verified=True)

        with patch("builtins.input") as prompt:
            self.assertFalse(offer_seven_zip_install(manager))

        prompt.assert_not_called()
        manager.install_seven_zip.assert_not_called()

    def test_declining_does_not_invoke_installer(self):
        manager = Mock()
        manager.get_tool_status.return_value = seven_zip_info(verified=False)

        with patch("builtins.input", return_value="N"):
            self.assertFalse(offer_seven_zip_install(manager))

        manager.install_seven_zip.assert_not_called()

    def test_accepting_invokes_installer(self):
        manager = Mock()
        manager.get_tool_status.return_value = seven_zip_info(verified=False)
        manager.install_seven_zip.return_value = True

        with patch("builtins.input", return_value="Y"):
            self.assertTrue(offer_seven_zip_install(manager))

        manager.install_seven_zip.assert_called_once_with()

    def test_missing_seven_zip_in_tool_status_offers_install(self):
        service = Mock(settings=Settings())
        service.tool_manager.get_tool_status.side_effect = lambda name: seven_zip_info(
            verified=name is not ToolName.SEVEN_ZIP
        )
        service.tool_manager.install_seven_zip.return_value = True

        with patch("builtins.input", return_value="Y"), patch("sys.stdout", new_callable=StringIO):
            CliSessionController(service).show_tool_status()

        service.tool_manager.install_seven_zip.assert_called_once_with()

    def test_installer_prefers_winget(self):
        manager = ToolManager(settings=Settings())
        with (
            patch("tools.tool_manager.shutil.which", return_value="winget.exe"),
            patch("tools.tool_manager.subprocess.run", return_value=Mock(returncode=0)) as run,
            patch.object(manager, "refresh_tool", return_value=True),
            patch.object(manager, "_download_and_run_7zip_installer") as download,
        ):
            self.assertTrue(manager.install_seven_zip())

        run.assert_called_once()
        self.assertEqual(run.call_args.args[0], manager.WINGET_INSTALL_COMMAND)
        download.assert_not_called()

    def test_installer_downloads_when_winget_fails(self):
        manager = ToolManager(settings=Settings())
        with (
            patch("tools.tool_manager.shutil.which", return_value="winget.exe"),
            patch("tools.tool_manager.subprocess.run", return_value=Mock(returncode=1)),
            patch.object(manager, "_download_and_run_7zip_installer") as download,
            patch.object(manager, "refresh_tool", return_value=True),
        ):
            self.assertTrue(manager.install_seven_zip())

        download.assert_called_once_with()

    def test_installer_downloads_only_when_winget_is_unavailable(self):
        manager = ToolManager(settings=Settings())
        with (
            patch("tools.tool_manager.shutil.which", return_value=None),
            patch.object(manager, "_download_and_run_7zip_installer") as download,
            patch.object(manager, "refresh_tool", return_value=True),
        ):
            self.assertTrue(manager.install_seven_zip())

        download.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
