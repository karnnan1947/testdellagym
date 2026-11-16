from datetime import date
from unittest.mock import MagicMock, patch

import requests

from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon

REQUEST_PATH = 'odoo.addons.dallah_gym_zkbio.models.zkbio_api_service.requests.request'


def _response(status=200, body=None):
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = body if body is not None else {'code': 0, 'data': {'id': 'P-1'}}
    resp.text = str(body)
    return resp


@tagged('post_install', '-at_install')
class TestZkbioApi(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.group_ids |= cls.env.ref('dallah_gym_core.group_gym_manager') | cls.env.ref('hr.group_hr_user')
        icp = cls.env['ir.config_parameter'].sudo()
        icp.set_str('dallah_gym_zkbio.server_ip', '192.168.1.100')
        icp.set_str('dallah_gym_zkbio.server_port', '8098')
        icp.set_str('dallah_gym_zkbio.api_token', 'zkbio_test_token')
        cls.bbm = cls.env['res.branch'].create({
            'name': "Izghawa Men's Gym", 'code': 'BBM',
            'zkbio_access_group_id': 'GRP_IZGHAWA_MEN', 'zkbio_device_ids': 'ProFace-BBM-01, ProFace-BBM-02',
        })
        cls.member = cls.env['res.partner'].create({
            'name': 'Nasser Al-Kuwari', 'is_gym_member': True, 'qid_number': '28563400000',
        })
        cls.plan = cls.env['product.product'].create({
            'name': '1 Month Gym', 'type': 'service', 'list_price': 300.0,
            'is_gym_membership': True, 'membership_type': 'gym',
            'membership_duration_val': 1, 'membership_duration_unit': 'months',
        })
        cls.Service = cls.env['gym.membership.service']
        cls.Queue = cls.env['zkbio.sync.queue']

    def _sell(self):
        return self.Service.finalize_membership_sale(
            self.member, self.plan, date(2026, 11, 10), allowed_branches=self.bbm, branch=self.bbm,
            amount_paid=300.0)

    # Task 5.1: offline queue resilience
    def test_offline_queue_resilience(self):
        with patch(REQUEST_PATH, side_effect=requests.exceptions.ConnectTimeout('timeout')):
            membership = self._sell()  # must not raise
        self.assertEqual(membership.state, 'active')
        queued = self.Queue.search([('partner_id', '=', self.member.id)])
        self.assertEqual(len(queued), 1)
        self.assertEqual(queued.state, 'pending')
        self.assertEqual(queued.action_type, 'sync')
        self.assertFalse(self.member.zkbio_synced)

    # Task 5.2: queue recovery
    def test_queue_recovery(self):
        with patch(REQUEST_PATH, side_effect=requests.exceptions.ConnectionError('down')):
            self._sell()
        queued = self.Queue.search([('partner_id', '=', self.member.id)])
        with patch(REQUEST_PATH, return_value=_response()) as mocked:
            with patch.object(type(self.env['zkbio.api.service']), 'fetch_realtime_gate_transactions',
                              return_value=self.env['gym.member.checkin']):
                self.env['zkbio.api.service']._cron_process_zkbio_sync()
        self.assertEqual(queued.state, 'done')
        self.assertTrue(self.member.zkbio_synced)
        payload = mocked.call_args.kwargs['json']
        self.assertEqual(payload['pin'], self.member.member_id_code)
        self.assertEqual(payload['access_groups'], ['GRP_IZGHAWA_MEN'])
        self.assertTrue(payload['enabled'])
        self.assertTrue(payload['end_time'].startswith('2026-12-09'))

    def test_freeze_suspends_and_refund_revokes(self):
        with patch(REQUEST_PATH, return_value=_response()) as mocked:
            membership = self._sell()
            self.env['gym.membership.freeze.wizard'].create({
                'membership_id': membership.id,
                'freeze_start_date': date(2026, 11, 20), 'freeze_end_date': date(2026, 11, 30),
            }).action_confirm_freeze()
            self.assertTrue(mocked.call_args.args[1].endswith('/api/v1/person/disable'))
            self.env['gym.membership.refund.wizard'].create({
                'membership_id': membership.id, 'cancellation_date': date(2026, 11, 15),
            }).action_execute_refund()
            self.assertTrue(mocked.call_args.args[1].endswith('/api/v1/person/delete_access'))

    # Task 5.3: scan importer, no duplicates
    def test_scan_importer(self):
        self.assertTrue(self.member.member_id_code)
        body = {'code': 0, 'data': [
            {'id': 'T1', 'pin': self.member.member_id_code, 'event_time': '2026-11-10 16:02:11',
             'device_name': 'ProFace-BBM-01', 'door_name': 'Turnstile Lane 1', 'verify_mode': 'Face',
             'result': 'granted'},
            {'id': 'T2', 'pin': self.member.member_id_code, 'event_time': '2026-11-10 16:05:00',
             'device_name': 'ProFace-BBM-02', 'verify_mode': 'Palm', 'result': 'denied'},
            {'id': 'T1', 'pin': self.member.member_id_code, 'event_time': '2026-11-10 16:02:11',
             'device_name': 'ProFace-BBM-01', 'verify_mode': 'Face', 'result': 'granted'},
        ]}
        Service = self.env['zkbio.api.service']
        with patch(REQUEST_PATH, return_value=_response(body=body)):
            first = Service.fetch_realtime_gate_transactions()
            second = Service.fetch_realtime_gate_transactions()
        self.assertEqual(len(first), 2)
        self.assertFalse(second)
        checkins = self.member.checkin_ids
        self.assertEqual(len(checkins), 2)
        self.assertEqual(set(checkins.mapped('access_result')), {'granted', 'denied'})
        self.assertEqual(checkins.branch_id, self.bbm)
