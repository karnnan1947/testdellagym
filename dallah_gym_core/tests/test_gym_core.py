from datetime import date
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestGymCore(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.group_ids |= cls.env.ref('dallah_gym_core.group_gym_manager') | cls.env.ref('hr.group_hr_user')
        cls.branch = cls.env['res.branch'].create({'name': "Izghawa Men's Gym", 'code': 'BBM'})
        cls.member = cls.env['res.partner'].create({'name': 'Nasser Al-Kuwari', 'is_gym_member': True})
        cls.plan_1m = cls.env['product.product'].create({
            'name': '1 Month Gym', 'type': 'service', 'list_price': 100.0,
            'is_gym_membership': True, 'membership_type': 'gym',
            'membership_duration_val': 1, 'membership_duration_unit': 'months',
        })
        cls.plan_30d = cls.env['product.product'].create({
            'name': '30 Days Gym', 'type': 'service', 'list_price': 100.0,
            'is_gym_membership': True, 'membership_type': 'gym',
            'membership_duration_val': 30, 'membership_duration_unit': 'days',
        })
        cls.coach = cls.env['hr.employee'].create({
            'name': 'Coach Alex Rodriguez', 'is_coach': True,
            'allowed_branch_ids': [(6, 0, cls.branch.ids)],
        })

    def _membership(self, product, start):
        return self.env['gym.membership'].create({
            'partner_id': self.member.id, 'product_id': product.id, 'start_date': start,
            'amount_paid': 100.0, 'branch_id': self.branch.id,
        })

    def test_member_code_sequence(self):
        self.assertTrue(self.member.member_id_code.startswith('GYM-'))

    # Task 5.1
    def test_auto_end_date(self):
        ms = self._membership(self.plan_1m, date(2026, 10, 22))
        self.assertEqual(ms.end_date, date(2026, 11, 21))
        service_end = self.env['gym.membership.service'].compute_end_date(self.plan_1m.id, '2026-10-22')
        self.assertEqual(service_end, date(2026, 11, 21))

    # Task 5.2
    def test_freeze_math(self):
        ms = self._membership(self.plan_1m, date(2026, 12, 1))
        original_end = ms.end_date
        wiz = self.env['gym.membership.freeze.wizard'].create({
            'membership_id': ms.id,
            'freeze_start_date': date(2026, 12, 15),
            'freeze_end_date': date(2027, 1, 4),
        })
        self.assertEqual(wiz.freeze_days, 21)
        wiz.action_confirm_freeze()
        self.assertEqual(ms.state, 'frozen')
        self.assertEqual(ms.end_date, fields.Date.add(original_end, days=21))
        self.assertEqual(len(ms.freeze_log_ids), 1)

    # Task 5.3
    def test_freeze_restoration_cron(self):
        ms = self._membership(self.plan_1m, date(2026, 12, 1))
        self.env['gym.membership.freeze.wizard'].create({
            'membership_id': ms.id,
            'freeze_start_date': date(2026, 12, 15),
            'freeze_end_date': date(2027, 1, 4),
        }).action_confirm_freeze()
        with patch.object(fields.Date, 'context_today', return_value=date(2027, 1, 5)):
            self.env['gym.membership']._cron_restore_frozen_memberships()
        self.assertEqual(ms.state, 'active')
        self.assertFalse(ms.is_frozen)

    # Task 5.4
    def test_pt_conflict_lock(self):
        Session = self.env['gym.pt.session']
        vals = {
            'partner_id': self.member.id, 'coach_id': self.coach.id, 'branch_id': self.branch.id,
            'session_date': date(2026, 11, 20), 'start_hour': 10.0, 'end_hour': 11.0,
        }
        Session.create(vals)
        other = self.env['res.partner'].create({'name': 'Other Member'})
        with self.assertRaises(ValidationError):
            Session.create(dict(vals, partner_id=other.id))

    # Task 5.5
    def test_pro_rata_refund(self):
        today = fields.Date.context_today(self.env['gym.membership'])
        ms = self._membership(self.plan_30d, fields.Date.subtract(today, days=9))  # today = day 10
        self.member.current_membership_id = ms
        wiz = self.env['gym.membership.refund.wizard'].create({'membership_id': ms.id})
        self.assertEqual(wiz.total_plan_days, 30)
        self.assertEqual(wiz.days_consumed, 10)
        self.assertAlmostEqual(wiz.calculated_refund_amount, 66.67, places=2)
        action = wiz.action_execute_refund()
        self.assertEqual(ms.state, 'cancelled')
        credit_note = self.env['account.move'].browse(action['res_id'])
        self.assertEqual(credit_note.move_type, 'out_refund')
        self.assertEqual(credit_note.state, 'draft')

    def test_finalize_generates_pt_sessions(self):
        pt = self.env['product.product'].create({
            'name': 'PT 26 Sessions', 'type': 'service', 'list_price': 1800.0,
            'is_gym_membership': True, 'membership_type': 'pt', 'pt_total_sessions': 26,
            'membership_duration_val': 1, 'membership_duration_unit': 'months',
        })
        ms = self.env['gym.membership.service'].finalize_membership_sale(
            self.member, pt, date(2026, 11, 10), allowed_branches=self.branch, branch=self.branch,
            coach=self.coach, slot_hour=19.0, amount_paid=1800.0)
        self.assertEqual(ms.end_date, date(2026, 12, 9))
        self.assertEqual(len(ms.pt_session_ids), 26)
        slots = self.env['gym.membership.service'].get_branch_coach_slots(
            self.branch.id, self.coach.id, '2026-11-10', 26, '2026-12-09')
        evening_19 = next(s for s in slots['evening'] if s['hour'] == 19.0)
        self.assertTrue(evening_19['booked'])
