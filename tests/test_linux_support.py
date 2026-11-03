"""Native Linux boundaries, runnable on Windows through platform simulation."""

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from application import runtime_paths as paths
from application.app_service import GameArchiveService
from config.settings import Settings
from gui import window_place
from main import offer_lz4_install, offer_seven_zip_install
from password.session_store import PasswordStoreError, SessionPasswordStore
from tools.models import ToolName
from tools.tool_manager import ToolManager
from version import APP_NAME


class LinuxSupportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        platform = patch('sys.platform', 'linux')
        platform.start()
        self.addCleanup(platform.stop)
        environment = patch.dict(os.environ, {
            'XDG_CONFIG_HOME': str(self.root / 'config'),
            'XDG_DATA_HOME': str(self.root / 'data'),
            'XDG_STATE_HOME': str(self.root / 'state'),
            'LOCALAPPDATA': str(self.root / 'windows'),
        })
        environment.start()
        self.addCleanup(environment.stop)

    def test_xdg_paths_and_writable_config_ignore_source_config(self):
        self.assertEqual(self.root / 'data' / APP_NAME, paths.user_data_directory())
        self.assertEqual(self.root / 'state' / APP_NAME / 'logs', paths.default_log_directory())
        self.assertEqual(self.root / 'data' / APP_NAME / 'history/task_history.json', paths.default_history_file())
        config = paths.default_config_path()
        self.assertEqual(self.root / 'config' / APP_NAME / 'config.json', config)
        self.assertTrue(config.parent.is_dir())
        self.assertFalse(config.exists())

    def test_relative_or_empty_xdg_variables_use_home_defaults(self):
        with patch.dict(os.environ, {'XDG_CONFIG_HOME': 'relative', 'XDG_DATA_HOME': '', 'XDG_STATE_HOME': '../bad'}), patch.object(Path, 'home', return_value=self.root):
            self.assertEqual(self.root / '.local/share' / APP_NAME, paths.user_data_directory())
            self.assertEqual(self.root / '.local/state' / APP_NAME / 'logs', paths.default_log_directory())
            self.assertEqual(self.root / '.config' / APP_NAME / 'config.json', paths.default_config_path())

    def test_windows_paths_still_prefer_portable_config(self):
        portable = self.root / 'config.json'
        portable.write_text('{}')
        with patch('sys.platform', 'win32'), patch.object(paths, 'application_directory', return_value=self.root):
            self.assertEqual(portable, paths.default_config_path())
            self.assertEqual(self.root / 'windows' / APP_NAME / 'logs', paths.default_log_directory())

    def native_file(self, name, contents=b'#!/bin/sh\n'):
        file = self.root / name
        file.write_bytes(contents)
        file.chmod(0o700)
        return file

    def test_native_alternative_names_are_discovered_and_verified(self):
        for name in ('7z', '7zz', '7za'):
            with self.subTest(name=name):
                native = self.native_file(name)
                lz4 = self.native_file('lz4')
                def which(value):
                    return str(native) if value == name else str(lz4) if value == 'lz4' else None
                ToolManager._verification_cache.clear()
                with patch('tools.tool_manager.shutil.which', side_effect=which), patch('tools.tool_manager.subprocess.run', side_effect=lambda argv, **kw: subprocess.CompletedProcess(argv, 0, '7-Zip 25.01' if argv[1] == 'i' else 'LZ4 v1.10.0', '')) as run:
                    manager = ToolManager(project_root=self.root)
                    self.assertTrue(manager.get_tool_status(ToolName.SEVEN_ZIP).verified)
                    self.assertEqual(native.resolve(), manager.get_tool_path(ToolName.SEVEN_ZIP))
                    self.assertTrue(manager.get_tool_status(ToolName.LZ4).verified)
                    self.assertIsNone(manager.get_tool_path(ToolName.WINRAR))
                    self.assertEqual(2, run.call_count)

    def test_windows_executables_and_winrar_are_never_launched(self):
        exe = self.native_file('7z.exe', b'MZfake')
        renamed = self.native_file('7zz', b'MZfake')
        with patch('tools.tool_manager.subprocess.run') as run:
            for value in (exe, renamed):
                manager = ToolManager({name: value for name in ToolName}, project_root=self.root)
                self.assertFalse(any(info.verified for info in manager.get_all_tool_statuses()))
            run.assert_not_called()

    def test_invalid_native_version_is_rejected_and_next_candidate_used(self):
        bad, good = self.native_file('7z'), self.native_file('7zz')
        with patch('tools.tool_manager.shutil.which', side_effect=lambda name: str({'7z': bad, '7zz': good}[name]) if name in ('7z', '7zz') else None), patch('tools.tool_manager.subprocess.run', side_effect=lambda argv, **kw: subprocess.CompletedProcess(argv, 0, 'unrelated 1.0' if argv[0] == str(bad.resolve()) else '7-Zip 25.01', '')):
            self.assertEqual(good.resolve(), ToolManager(project_root=self.root).get_tool_path(ToolName.SEVEN_ZIP))

    def test_linux_install_paths_do_not_prompt_download_or_run_winget(self):
        with patch('tools.tool_manager.shutil.which', return_value=None):
            manager = ToolManager(project_root=self.root)
        with patch('builtins.input') as prompt, patch('tools.tool_manager.subprocess.run') as run, patch('tools.tool_manager.build_opener') as opener:
            self.assertFalse(offer_seven_zip_install(manager))
            self.assertFalse(offer_lz4_install(manager))
            self.assertFalse(manager.install_seven_zip())
            self.assertFalse(manager.install_lz4())
            prompt.assert_not_called()
            run.assert_not_called()
            opener.assert_not_called()

    def test_no_secret_tool_allows_service_and_session_but_never_persistence(self):
        with patch('password.session_store.shutil.which', return_value=None), patch('tools.tool_manager.shutil.which', return_value=None):
            service = GameArchiveService(settings=Settings())
            store = service.session_password_store
            store.add_verified('session-fixture', persist=True)
            self.assertEqual(['session-fixture'], store.verified_passwords())
            self.assertIsNotNone(store.last_persistence_error)
            with self.assertRaises(PasswordStoreError):
                store.replace(['persist-fixture'])
            self.assertFalse(store.path.exists())

    def test_secret_service_roundtrip_stdin_and_no_plaintext_files(self):
        path = self.root / 'library.json'
        payload = None
        def execute(argv, **kwargs):
            nonlocal payload
            self.assertNotIn('unicode-fixture-中文', ' '.join(argv))
            if argv[1] == 'store':
                payload = kwargs['input']
                return subprocess.CompletedProcess(argv, 0, '', '')
            return subprocess.CompletedProcess(argv, 0 if payload else 1, payload or '', '')
        with patch('password.session_store.shutil.which', return_value='/usr/bin/secret-tool'), patch('password.session_store.subprocess.run', side_effect=execute):
            store = SessionPasswordStore(path)
            store.replace(['unicode-fixture-中文', 'line\nbreak', 'unicode-fixture-中文'])
            self.assertEqual(['unicode-fixture-中文', 'line\nbreak'], SessionPasswordStore(path).passwords())
            for file in self.root.rglob('*'):
                if file.is_file():
                    self.assertNotIn(b'unicode-fixture', file.read_bytes())

    def test_no_secret_service_allows_fresh_boot_and_session_only(self):
        with patch('password.session_store.shutil.which', return_value='/usr/bin/secret-tool'), patch('password.session_store.subprocess.run', return_value=subprocess.CompletedProcess([], 1, '', 'No service raw-secret-fixture')):
            service = GameArchiveService(settings=Settings())
            store = service.session_password_store
            self.assertEqual([], store.passwords())
            store.add_verified('session-fixture', persist=True)
            self.assertEqual(['session-fixture'], store.verified_passwords())
            self.assertTrue(store.last_persistence_error)
            self.assertNotIn('raw-secret-fixture', store.last_persistence_error)
            with self.assertRaises(PasswordStoreError) as raised:
                store.replace(['persist-fixture'])
            self.assertNotIn('raw-secret-fixture', str(raised.exception))
            self.assertFalse(store.path.exists())
            self.assertEqual([], SessionPasswordStore(store.path).passwords())

    def test_first_store_failure_never_creates_marker_and_restart_can_boot(self):
        path = self.root / 'library.json'
        failures = (subprocess.CompletedProcess([], 1, '', 'raw-secret-fixture'),
                    FileNotFoundError('raw-secret-fixture'),
                    subprocess.TimeoutExpired('secret-tool', 15, output='raw-secret-fixture'))
        for failure in failures:
            with self.subTest(failure=type(failure).__name__), patch('password.session_store.shutil.which', return_value='/usr/bin/secret-tool'):
                with patch('password.session_store.subprocess.run', return_value=subprocess.CompletedProcess([], 1, '', '')):
                    store = SessionPasswordStore(path)
                def fail_store(argv, **kwargs):
                    self.assertFalse(path.exists())
                    if isinstance(failure, Exception):
                        raise failure
                    return failure
                with patch('password.session_store.subprocess.run', side_effect=fail_store):
                    with self.assertRaises(PasswordStoreError) as raised:
                        store.replace(['persist-fixture'])
                self.assertNotIn('raw-secret-fixture', str(raised.exception))
                self.assertFalse(path.exists())
                self.assertEqual([], store.passwords())
                with patch('password.session_store.subprocess.run', return_value=subprocess.CompletedProcess([], 1, '', 'No service raw-secret-fixture')):
                    self.assertEqual([], SessionPasswordStore(path).passwords())

    def test_fresh_lookup_execution_failure_allows_session_but_save_is_sanitized(self):
        with patch('password.session_store.shutil.which', return_value='/usr/bin/secret-tool'), patch('password.session_store.subprocess.run', side_effect=FileNotFoundError('raw-secret-fixture')):
            store = SessionPasswordStore(self.root / 'library.json')
            store.add_verified('session-fixture', persist=True)
            self.assertEqual(['session-fixture'], store.verified_passwords())
            self.assertTrue(store.last_persistence_error)
            self.assertNotIn('raw-secret-fixture', store.last_persistence_error)
            self.assertFalse(store.path.exists())

    def test_successful_secret_survives_marker_creation_failure(self):
        path = self.root / 'library.json'
        with patch('password.session_store.shutil.which', return_value=None):
            store = SessionPasswordStore(path)
        payload = None
        def execute(argv, **kwargs):
            nonlocal payload
            if argv[1] == 'store':
                payload = kwargs['input']
                return subprocess.CompletedProcess(argv, 0, '', '')
            return subprocess.CompletedProcess(argv, 0, payload, '')
        with patch('password.session_store.shutil.which', return_value='/usr/bin/secret-tool'), patch('password.session_store.subprocess.run', side_effect=execute):
            original_open = Path.open
            def open_marker(file, mode='r', *args, **kwargs):
                if mode == 'x':
                    raise PermissionError('raw-secret-fixture')
                return original_open(file, mode, *args, **kwargs)
            with patch.object(Path, 'open', open_marker):
                with self.assertRaises(PasswordStoreError) as raised:
                    store.replace(['persist-fixture'])
            self.assertNotIn('raw-secret-fixture', str(raised.exception))
            self.assertFalse(path.exists())
            self.assertEqual([], store.passwords())
            self.assertEqual(['persist-fixture'], SessionPasswordStore(path).passwords())

    def test_fresh_gui_boots_without_secret_service(self):
        import tkinter as tk
        from gui import app as module

        root = tk.Tk()
        self.addCleanup(root.destroy)
        with patch('password.session_store.shutil.which', return_value='/usr/bin/secret-tool'), patch('password.session_store.subprocess.run', return_value=subprocess.CompletedProcess([], 1, '', 'No service raw-secret-fixture')), patch.object(module.window_place, 'restore_maximized'), patch.object(module.window_place, 'geometry_for', return_value='720x520+80+80'):
            app = module.GameArchiveApp(root)
            root.update()
            self.assertTrue(app.library_button.winfo_exists())

    def test_existing_marker_missing_locked_or_malformed_secret_fails_closed(self):
        path = self.root / 'library.json'
        path.write_text(json.dumps({'version': 1, 'backend': 'secret-service'}))
        for response in (None, subprocess.CompletedProcess([], 1, '', ''), subprocess.CompletedProcess([], 1, '', 'locked secret-fixture'), subprocess.CompletedProcess([], 0, 'not json secret-fixture', '')):
            with self.subTest(response=response), patch('password.session_store.shutil.which', return_value=None if response is None else '/usr/bin/secret-tool'), patch('password.session_store.subprocess.run', return_value=response):
                with self.assertRaises(PasswordStoreError) as raised:
                    SessionPasswordStore(path)
                self.assertNotIn('secret-fixture', str(raised.exception))

    def test_secret_service_failure_preserves_library_and_memory(self):
        path = self.root / 'library.json'
        with patch('password.session_store.shutil.which', return_value='/usr/bin/secret-tool'), patch('password.session_store.subprocess.run', return_value=subprocess.CompletedProcess([], 1, '', '')):
            store = SessionPasswordStore(path)
        with patch('password.session_store.shutil.which', return_value='/usr/bin/secret-tool'), patch('password.session_store.subprocess.run', side_effect=subprocess.TimeoutExpired('secret-tool', 10, output='secret-fixture')):
            with self.assertRaises(PasswordStoreError) as raised:
                store.replace(['secret-fixture'])
            self.assertEqual([], store.passwords())
            self.assertNotIn('secret-fixture', str(raised.exception))

    def test_linux_maximize_is_remembered_and_restored_using_tk_attribute(self):
        widget = Mock()
        widget.winfo_x.return_value = widget.winfo_y.return_value = 10
        widget.winfo_width.return_value = 900
        widget.winfo_height.return_value = 520
        widget.state.return_value = 'normal'
        widget.attributes.return_value = 1
        with patch.object(window_place, '_load', return_value={}), patch.object(window_place, '_save') as save:
            window_place.remember('main', widget)
            self.assertTrue(save.call_args.args[0]['main']['maximized'])
        with patch.object(window_place, '_load', return_value={'main': {'x': 10, 'y': 10, 'maximized': True}}), patch.object(window_place, '_on_screen', return_value=True):
            window_place.restore_maximized('main', widget)
        widget.attributes.assert_called_with('-zoomed', True)
        widget.state.assert_not_called()

    def test_unsupported_linux_maximize_does_not_crash(self):
        widget = Mock()
        import tkinter
        widget.attributes.side_effect = tkinter.TclError('unsupported')
        with patch.object(window_place, '_load', return_value={'main': {'x': 1, 'y': 1, 'maximized': True}}), patch.object(window_place, '_on_screen', return_value=True):
            window_place.restore_maximized('main', widget)

    def test_unsupported_zoom_attribute_still_remembers_normal_geometry(self):
        import tkinter
        widget = Mock()
        widget.winfo_x.return_value = widget.winfo_y.return_value = 10
        widget.winfo_width.return_value = 900
        widget.winfo_height.return_value = 520
        widget.attributes.side_effect = tkinter.TclError('unsupported')
        with patch.object(window_place, '_load', return_value={}), patch.object(window_place, '_save') as save:
            window_place.remember('main', widget)
            self.assertFalse(save.call_args.args[0]['main']['maximized'])

    def test_oversized_secret_is_rejected_before_touching_keyring_or_marker(self):
        path = self.root / 'library.json'
        with patch('password.session_store.shutil.which', return_value=None):
            store = SessionPasswordStore(path)
        with patch('password.session_store.shutil.which', return_value='/usr/bin/secret-tool'), patch('password.session_store.subprocess.run') as run:
            with self.assertRaises(PasswordStoreError):
                store.replace(['中' * 8192])
            run.assert_not_called()
        self.assertFalse(path.exists())

    def test_failed_update_keeps_previous_keyring_values_marker_and_session(self):
        path = self.root / 'library.json'
        path.write_text(json.dumps({'version': 1, 'backend': 'secret-service'}))
        before = path.read_bytes()
        responses = [subprocess.CompletedProcess([], 0, '["old-fixture"]', ''), subprocess.CompletedProcess([], 0, '["old-fixture"]', ''), subprocess.CompletedProcess([], 1, '', 'locked new-fixture')]
        with patch('password.session_store.shutil.which', return_value='/usr/bin/secret-tool'), patch('password.session_store.subprocess.run', side_effect=responses):
            store = SessionPasswordStore(path)
            store.add_verified('session-fixture')
            with self.assertRaises(PasswordStoreError) as raised:
                store.replace(['new-fixture'])
        self.assertEqual(['old-fixture'], store.passwords())
        self.assertEqual(['session-fixture'], store.verified_passwords())
        self.assertEqual(before, path.read_bytes())
        self.assertNotIn('new-fixture', str(raised.exception))

    def test_foreign_password_file_is_preserved_without_keyring_access(self):
        path = self.root / 'windows-library.json'
        original = b'{"version":1,"protected_passwords":"AA=="}'
        path.write_bytes(original)
        with patch('password.session_store.subprocess.run') as run:
            with self.assertRaises(PasswordStoreError):
                SessionPasswordStore(path)
            run.assert_not_called()
        self.assertEqual(original, path.read_bytes())

    def test_native_tool_timeout_or_non_executable_never_verifies(self):
        native = self.native_file('7z')
        ToolManager._verification_cache.clear()
        with patch('tools.tool_manager.subprocess.run', side_effect=subprocess.TimeoutExpired('7z', 5)):
            manager = ToolManager({ToolName.SEVEN_ZIP: native}, project_root=self.root)
            self.assertFalse(manager.get_tool_status(ToolName.SEVEN_ZIP).verified)
        with patch('tools.tool_manager.os.access', return_value=False), patch('tools.tool_manager.subprocess.run') as run:
            manager = ToolManager({ToolName.SEVEN_ZIP: native}, project_root=self.root)
            self.assertFalse(manager.get_tool_status(ToolName.SEVEN_ZIP).verified)
            run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
