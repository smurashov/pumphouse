import yaml
import unittest
from pumphouse import utils
import pumphouse.exceptions as excs
from mock import Mock, patch, mock_open


class DummyClass():
    pass


class TestSafeLoadYaml(unittest.TestCase):

    @patch.object(yaml, "safe_load")
    def test_safe_load_yaml(self, mock_safe_load):
        filename = "dummy.yaml"
        m = mock_open()

        with patch('__builtin__.open', m, create=False):
            utils.safe_load_yaml(filename)

        m.assert_called_once_with(filename)
        mock_safe_load.assert_called_once_with(m())


class TestLoadClass(unittest.TestCase):
    def setUp(self):
        self.correct_import_path = "tests.unit.test_utils.DummyClass"
        self.incorrect_import_path = "tests.unit.dummy.DummyClass"

    def test_load_class(self):
        self.assertEqual(
            utils.load_class(self.correct_import_path),
            DummyClass
        )

    def test_load_class_exc(self):
        with self.assertRaises(ImportError) as ec:
            utils.load_class(self.incorrect_import_path)
        self.assertEqual(ec.exception.args[0], "No module named dummy")


class TestWaitFor(unittest.TestCase):
    def setUp(self):
        self.attr = "dummy_attr"
        self.value = "UP"
        self.timeout = 150
        self.check_interval = 1

        self.resource = Mock()
        self.upd_resource = Mock()
        self.upd_resource.dummy_attr.return_value = self.attr
        self.upd_resource.status.return_value = "status"

        self.update_resource = Mock(return_value=self.upd_resource)
        self.attribute_getter = Mock(return_value=self.attr)
        self.attribute_getter.return_value = self.value

        time_patcher = patch("pumphouse.utils.time")
        self.time = time_patcher.start()
        self.time.time.side_effect = [100, 200, 300]

    def test_wait_for_success_on_first_pass(self):
        result = utils.wait_for(
            self.resource,
            self.update_resource,
            attribute_getter=self.attribute_getter,
            value=self.value,
            timeout=self.timeout,
            check_interval=self.check_interval
        )
        self.update_resource.assert_called_once_with(self.resource)
        self.attribute_getter.assert_called_once_with(self.upd_resource)
        self.assertEqual(result, self.upd_resource)

    def test_wait_for_stop_exception(self):
        self.update_resource.side_effect = Exception("This should be caught")
        result = utils.wait_for(
            self.resource,
            self.update_resource,
            attribute_getter=self.attribute_getter,
            value=self.value,
            timeout=self.timeout,
            check_interval=self.check_interval,
            stop_excs=(Exception,)
        )
        self.assertEqual(result, None)

    def test_wait_for_expected_exception(self):
        self.update_resource.side_effect = (Exception, self.upd_resource)
        result = utils.wait_for(
            self.resource,
            self.update_resource,
            attribute_getter=self.attribute_getter,
            value=self.value,
            timeout=self.timeout,
            check_interval=self.check_interval,
            expect_excs=(Exception,)
        )
        self.assertEqual(result, self.upd_resource)

    def test_wait_for_value_and_timeout(self):
        with self.assertRaises(excs.TimeoutException):
            utils.wait_for(
                self.resource,
                self.update_resource,
                attribute_getter=self.attribute_getter,
                timeout=self.timeout,
                check_interval=self.check_interval
            )

if __name__ == '__main__':
    unittest.main()
