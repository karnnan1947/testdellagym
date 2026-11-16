from datetime import date

from odoo import Command, fields
from odoo.tests import tagged

from odoo.addons.point_of_sale.tests.common import TestPoSCommon


@tagged('post_install', '-at_install')
class TestGymPos(TestPoSCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.group_ids |= cls.env.ref('dallah_gym_core.group_gym_manager') | cls.env.ref('hr.group_hr_user')
        Branch = cls.env['res.branch']
        cls.bbm = Branch.create({'name': "Izghawa Men's Gym", 'code': 'BBM'})
        cls.bbu = Branch.create({'name': "Mashaff Men's Gym", 'code': 'BBU'})
        cls.uhd = Branch.create({'name': "Markhiya Men's Gym", 'code': 'UHD'})
        cls.ladies = Branch.create({'name': 'Al Rayyan Ladies Gym', 'code': 'LAD'})
        cls.config = cls.basic_config
        cls.config.write({
            'gym_branch_id': cls.bbm.id,
            'default_allowed_branch_ids': [Command.set((cls.bbm | cls.bbu | cls.uhd).ids)],
        })
        cls.member = cls.env['res.partner'].create({'name': 'Nasser Al-Kuwari', 'is_gym_member': True})
        cls.coach = cls.env['hr.employee'].create({
            'name': 'Coach Alex Rodriguez', 'is_coach': True, 'allowed_branch_ids': [Command.set(cls.bbm.ids)],
        })
        cls.plan_6m = cls.create_product('6 Months Full Gym', cls.categ_basic, 2500.0)
        cls.plan_6m.product_tmpl_id.write({
            'is_gym_membership': True, 'membership_type': 'gym',
            'membership_duration_val': 6, 'membership_duration_unit': 'months',
        })
        cls.pt_26 = cls.create_product('PT 26', cls.categ_basic, 1800.0)
        cls.pt_26.product_tmpl_id.write({
            'is_gym_membership': True, 'membership_type': 'pt', 'pt_total_sessions': 26,
            'membership_duration_val': 1, 'membership_duration_unit': 'months',
        })
        cls.water = cls.create_product('Bottled Water', cls.categ_basic, 2.0)

    def _sync(self, order_data):
        return self.env['pos.order'].sync_from_ui([order_data])['pos.order'][0]['id']

    # Task 5.1 (backend side): cafeteria items are not gym products, no membership created
    def test_cafeteria_bypass(self):
        self.assertFalse(self.water.is_gym_membership)
        self.open_new_session()
        order = self.env['pos.order'].browse(self._sync(
            self.create_ui_order_data([(self.water, 1)], customer=self.member)))
        self.assertEqual(order.state, 'paid')
        self.assertFalse(self.env['gym.membership'].search([('partner_id', '=', self.member.id)]))

    # Task 5.2: counter defaults are part of the POS startup payload
    def test_counter_defaults_loaded(self):
        self.open_new_session()
        data = self.pos_session.load_data({'models': ['pos.config', 'res.branch', 'product.template']})
        config_rec = data['pos.config'][0] if isinstance(data['pos.config'], list) else data['pos.config']['records'][0]
        self.assertEqual(config_rec['gym_branch_id'], self.bbm.id)
        self.assertEqual(set(config_rec['default_allowed_branch_ids']), set((self.bbm | self.bbu | self.uhd).ids))
        self.assertNotIn(self.ladies.id, config_rec['default_allowed_branch_ids'])

    # Task 5.3: second terminal sees the coach slot locked
    def test_multi_terminal_slot_lock(self):
        self.open_new_session()
        start = fields.Date.context_today(self.env['pos.order'])
        line_vals = {
            'product': self.pt_26, 'quantity': 1,
            'membership_start_date': fields.Date.to_string(start),
            'membership_end_date': fields.Date.to_string(fields.Date.add(start, months=1, days=-1)),
            'coach_id': self.coach.id, 'pt_slot_hour': 10.0,
        }
        self._sync(self.create_ui_order_data([line_vals], customer=self.member, pos_order_ui_args={
            'gym_branch_id': self.bbm.id, 'allowed_branch_ids': [Command.set(self.bbm.ids)],
        }))
        slots = self.env['gym.membership.service'].get_branch_coach_slots(
            self.bbm.id, self.coach.id, fields.Date.to_string(start), 26, line_vals['membership_end_date'])
        slot_10 = next(s for s in slots['morning'] if s['hour'] == 10.0)
        self.assertTrue(slot_10['booked'], "Second terminal must see 10:00-11:00 locked (red)")

    def test_paid_order_creates_membership(self):
        self.open_new_session()
        order_id = self._sync(self.create_ui_order_data([{
            'product': self.plan_6m, 'quantity': 1,
            'membership_start_date': '2026-11-10', 'membership_end_date': '2027-05-09',
        }], customer=self.member, pos_order_ui_args={
            'gym_branch_id': self.bbm.id,
            'allowed_branch_ids': [Command.set((self.bbm | self.bbu).ids)],
        }))
        order = self.env['pos.order'].browse(order_id)
        self.assertTrue(order.gym_membership_finalized)
        membership = self.member.current_membership_id
        self.assertEqual(membership.product_id, self.plan_6m)
        self.assertEqual(membership.end_date, date(2027, 5, 9))
        self.assertEqual(self.member.allowed_branch_ids, self.bbm | self.bbu)
