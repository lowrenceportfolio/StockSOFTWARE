import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError

from core import Store
from cloud import (Supabase, CloudError, Conflict, snapshot, digest,
                   apply_snapshot, read_baseline, save_baseline, PROJECT_URL)


class CloudTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / 'local.sqlite3')
        self.client = Supabase(PROJECT_URL)
        self.client.user_id = 'test-user'
        self.calls = []

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def item(self):
        return self.store.add_item(dict(title='Felpa', cost='7', asking='15'))

    def fake(self, remote, patched=None):
        def request(path, method='GET', body=None):
            self.calls.append((path, method, body))
            if method == 'GET':
                return remote
            if method == 'PATCH':
                return patched if patched is not None else [dict(revision=3)]
            return [dict(revision=1)]
        self.client.request = request

    def test_full_roundtrip_including_photos_and_shipments(self):
        ident = self.item()
        self.store.record_sale(ident, '2026-10-14', '15', '0', '0', 'In attesa')
        with self.store.db:
            self.store.db.execute('INSERT INTO photos(item_id,name,data,created_at) VALUES (?,?,?,?)',
                                  (ident, 'photo.jpg', b'photo bytes', '2026-10-14'))
        payload = snapshot(self.store)
        self.store.add_expense('2026-10-14', 'Local expense', '2')
        safety = apply_snapshot(self.store, payload)
        self.assertTrue(safety.exists())
        self.assertEqual(snapshot(self.store), payload)
        self.assertEqual(self.store.photo_data(1), b'photo bytes')

    def test_invalid_foreign_key_rolls_back_all_tables(self):
        self.item()
        before = snapshot(self.store)
        broken = copy.deepcopy(before)
        broken['tables']['items'][0]['lot_id'] = 999
        with self.assertRaises(CloudError):
            apply_snapshot(self.store, broken)
        self.assertEqual(before, snapshot(self.store))

    def test_missing_table_is_rejected_before_replacement(self):
        self.item()
        before = snapshot(self.store)
        broken = copy.deepcopy(before)
        del broken['tables']['photos']
        with self.assertRaises(CloudError):
            apply_snapshot(self.store, broken)
        self.assertEqual(before, snapshot(self.store))

    def test_new_cloud_uploads_existing_local_data(self):
        self.item()
        payload = snapshot(self.store)
        self.fake([])
        self.assertEqual(self.client.exchange(payload, None), ('push', 1, payload))
        self.assertEqual(self.calls[-1][1], 'POST')

    def test_empty_new_device_downloads_existing_cloud(self):
        local = snapshot(self.store)
        self.item()
        remote = snapshot(self.store)
        self.fake([dict(revision=2, payload=remote)])
        self.assertEqual(self.client.exchange(local, None), ('pull', 2, remote))

    def test_first_link_never_overwrites_different_existing_data(self):
        self.item()
        local = snapshot(self.store)
        self.fake([dict(revision=2, payload=dict(format=1, tables={t: [] for t in local['tables']}))])
        with self.assertRaises(Conflict):
            self.client.exchange(local, None)
        self.assertEqual(len(self.calls), 1)

    def test_unmodified_local_downloads_new_revision(self):
        local = snapshot(self.store)
        self.item()
        remote = snapshot(self.store)
        self.fake([dict(revision=2, payload=remote)])
        self.assertEqual(self.client.exchange(local, dict(revision=1, digest=digest(local))), ('pull', 2, remote))

    def test_concurrent_edits_are_never_overwritten(self):
        old = snapshot(self.store)
        self.item()
        local = snapshot(self.store)
        self.fake([dict(revision=3, payload=old)])
        with self.assertRaises(Conflict):
            self.client.exchange(local, dict(revision=2, digest=digest(old)))
        self.assertEqual(len(self.calls), 1)

    def test_upload_uses_compare_and_swap(self):
        old = snapshot(self.store)
        self.item()
        local = snapshot(self.store)
        self.fake([dict(revision=2, payload=old)])
        result = self.client.exchange(local, dict(revision=2, digest=digest(old)))
        self.assertEqual(result[0], 'push')
        self.assertIn('&revision=eq.2', self.calls[-1][0])

    def test_update_race_is_reported(self):
        old = snapshot(self.store)
        self.item()
        self.fake([dict(revision=2, payload=old)], patched=[])
        with self.assertRaises(Conflict):
            self.client.exchange(snapshot(self.store), dict(revision=2, digest=digest(old)))

    def test_lost_upload_response_is_reconciled_without_duplicates(self):
        self.item()
        local = snapshot(self.store)
        self.fake([dict(revision=2, payload=local)])
        self.assertEqual(self.client.exchange(local, None)[0], 'same')
        self.assertEqual(len(self.calls), 1)

    def test_baselines_are_specific_to_account_and_database(self):
        self.assertIsNone(read_baseline(self.store, 'account-1'))
        save_baseline(self.store, 'account-1', 2, 'digest')
        self.assertIsNone(read_baseline(self.store, 'account-2'))
        self.assertEqual(read_baseline(self.store, 'account-1'), dict(revision=2, digest='digest'))

    def test_network_failure_keeps_database(self):
        self.item()
        before = snapshot(self.store)
        with patch('cloud.urlopen', side_effect=URLError('offline')):
            with self.assertRaises(CloudError):
                self.client.exchange(before, None)
        self.assertEqual(before, snapshot(self.store))

    def test_rejects_non_supabase_or_insecure_url(self):
        for url in ('http://test.supabase.co', 'https://test.supabase.co.evil.com',
                    'https://evil.com', 'https://test.supabase.co/path'):
            with self.assertRaises(CloudError):
                Supabase(url)

    def test_publishable_key_is_not_used_as_bearer_token(self):
        with patch('cloud.urlopen') as opening:
            opening.return_value.__enter__.return_value.read.return_value = b'{}'
            self.client.request('/auth/v1/signup', 'POST', {})
            req = opening.call_args.args[0]
            self.assertEqual(req.get_header('Apikey'), self.client.key)
            self.assertIsNone(req.get_header('Authorization'))


if __name__ == '__main__':
    unittest.main()
