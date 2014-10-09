import unittest

import mock

from pumphouse.tasks import utils


class MemorizedUploadReporter(utils.UploadReporter):
    def report(self, absolute):
        self.context.append(absolute)


class UploadReporterTestCase(unittest.TestCase):
    def setUp(self):
        self.reports = []
        self.reporter = MemorizedUploadReporter(self.reports)

    def test_update(self):
        self.reporter.set_size(1024)
        [self.reporter.update(64) for _ in xrange(1, 17)]
        expected = [0.125, 0.25, 0.3125, 0.4375, 0.5625,
                    0.625, 0.75, 0.8125, 0.9375, 1.0]
        self.assertEqual(expected, self.reports)

    def test_zero_size(self):
        self.reporter.update(1024)
        self.assertEqual([], self.reports)


class SyncPointTestCase(unittest.TestCase):
    def setUp(self):
        self.point = utils.SyncPoint(name="fpoint")

    # NOTE(akscram): This is a contrived test.
    @mock.patch("pumphouse.tasks.utils.LOG.debug")
    def test_sync_point(self, mock_debug):
        self.point.execute(fake="fake")
        mock_debug.assert_called_once_with(mock.ANY, mock.ANY, mock.ANY)


class FileProxyTestCase(unittest.TestCase):
    def setUp(self):
        self.data = mock.Mock()
        self.resp = self.data._resp
        self.resp.getheader.return_value = "1024"
        self.resp.read.side_effect = ["*" * 512] + ["*" * 512] + [None]
        self.reporter = mock.Mock()
        self.fproxy = utils.FileProxy(self.data, self.reporter)

    def test_read(self):
        chunk_one = self.fproxy.read(512)
        chunk_two = self.fproxy.read(512)
        chunk_none = self.fproxy.read(512)
        chunk_data = "*" * 512
        self.assertEqual(chunk_data, chunk_one)
        self.assertEqual(chunk_data, chunk_two)
        self.assertIsNone(chunk_none)
        chunk_calls = [mock.call(512), mock.call(512)]
        self.reporter.update.assert_calls(chunk_calls)
        self.resp.read.assert_calls(chunk_calls + [mock.call(512)])

    def test_close(self):
        self.fproxy.close()
        self.resp.close.assert_called_once_with()

    def test_isclosed(self):
        self.resp.isclosed.return_value = True
        isclosed = self.fproxy.isclosed()
        self.assertTrue(isclosed)
