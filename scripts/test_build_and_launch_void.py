import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch
import subprocess
import signal

spec = importlib.util.spec_from_file_location('deploy', Path(__file__).with_name('build-and-launch-void.py'))
deploy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deploy)


class ModernUIShadowTest(unittest.TestCase):
    def test_preserves_other_settings_and_is_idempotent(self):
        original = '# comment\n[text]\n\tallowShadow = true # shadow\nbaseFontSize = 8.0\n[other]\nflag = true\n'
        expected = original.replace('allowShadow = true', 'allowShadow = false')
        self.assertEqual(deploy.without_modern_ui_shadow(original), expected)
        self.assertEqual(deploy.without_modern_ui_shadow(expected), expected)

    def test_rejects_invalid_setting(self):
        with self.assertRaises(RuntimeError):
            deploy.without_modern_ui_shadow('[text]\nallowShadow = "true"\n')


class InstanceRestartTest(unittest.TestCase):
    def test_selects_only_target_minecraft(self):
        processes = ('11 /jdk/bin/java org.prismlauncher.EntryPoint\n'
                     '22 /jdk/bin/java org.prismlauncher.EntryPoint\n'
                     '33 /jdk/bin/java org.gradle.launcher.daemon.bootstrap.GradleDaemon\n')
        def cwd(command, **kwargs):
            directory = deploy.INSTANCE / 'minecraft' if command[3] == '11' else Path('/other/instance/minecraft')
            return subprocess.CompletedProcess(command, 0, f'p{command[3]}\nfcwd\nn{directory}\n', '')
        with patch.object(deploy.subprocess, 'check_output', return_value=processes), \
                patch.object(deploy.subprocess, 'run', side_effect=cwd):
            self.assertEqual(deploy.instance_pids(), [11])

    def test_sigterm_and_wait_for_exit(self):
        with patch.object(deploy, 'instance_pids', side_effect=[[11], [11], [11], []]), \
                patch.object(deploy.os, 'kill') as kill, patch.object(deploy.time, 'sleep') as sleep:
            deploy.stop_instance()
        kill.assert_called_once_with(11, signal.SIGTERM)
        sleep.assert_called_once_with(0.25)

    def test_timeout_does_not_force_kill(self):
        with patch.object(deploy, 'instance_pids', return_value=[11]), \
                patch.object(deploy.os, 'kill') as kill, \
                patch.object(deploy.time, 'monotonic', side_effect=[0, 31]):
            with self.assertRaisesRegex(RuntimeError, 'without forcing termination'):
                deploy.stop_instance()
        kill.assert_called_once_with(11, signal.SIGTERM)

    def test_disappeared_process_is_not_signaled(self):
        with patch.object(deploy, 'instance_pids', side_effect=[[11], [], []]), \
                patch.object(deploy.os, 'kill') as kill:
            deploy.stop_instance()
        kill.assert_not_called()


if __name__ == '__main__':
    unittest.main()
