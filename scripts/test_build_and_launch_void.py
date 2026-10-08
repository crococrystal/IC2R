import importlib.util
from pathlib import Path
import unittest

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


if __name__ == '__main__':
    unittest.main()
