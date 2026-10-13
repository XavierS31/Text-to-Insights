from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pv_pipeline.zotero import ZoteroReader


class ZoteroTests(unittest.TestCase):
    def test_storage_redirect_does_not_receive_api_key(self):
        reader = ZoteroReader('test-secret')
        redirect = Mock(is_redirect=True, headers={'Location': 'https://storage.example/paper'})
        storage = Mock()
        storage.iter_content.return_value = [b'%PDF-1.7\nexample']
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'paper.pdf'
            with patch.object(reader, 'get', return_value=redirect), patch(
                    'pv_pipeline.zotero.requests.get', return_value=storage) as remote:
                reader.download_pdf('1', 'ABCDEFGH', target)
            self.assertEqual(target.read_bytes(), b'%PDF-1.7\nexample')
            self.assertNotIn('headers', remote.call_args.kwargs)

    def test_invalid_pdf_is_not_saved(self):
        reader = ZoteroReader('test-secret')
        response = Mock(is_redirect=False)
        response.iter_content.return_value = [b'<html>Not a PDF</html>']
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'paper.pdf'
            with patch.object(reader, 'get', return_value=response), self.assertRaises(ValueError):
                reader.download_pdf('1', 'ABCDEFGH', target)
            self.assertFalse(target.exists())
            self.assertFalse(target.with_suffix('.pdf.part').exists())

    def test_pagination_reads_all_pages(self):
        reader = ZoteroReader('test-secret')
        first, second = Mock(), Mock()
        first.headers = second.headers = {'Total-Results': '3'}
        first.json.return_value = [{'key': 'A'}, {'key': 'B'}]
        second.json.return_value = [{'key': 'C'}]
        first.__enter__ = Mock(return_value=first)
        first.__exit__ = Mock(return_value=False)
        second.__enter__ = Mock(return_value=second)
        second.__exit__ = Mock(return_value=False)
        with patch.object(reader, 'get', side_effect=[first, second]) as get:
            self.assertEqual(len(reader.all('/groups/1/items/top')), 3)
            self.assertEqual(get.call_args.kwargs['params']['start'], 2)


if __name__ == '__main__':
    unittest.main()
