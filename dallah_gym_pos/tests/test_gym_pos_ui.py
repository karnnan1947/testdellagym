from odoo import Command
from odoo.tests import tagged

from odoo.addons.point_of_sale.tests.test_frontend import TestPointOfSaleHttpCommon


@tagged('post_install', '-at_install')
class TestGymPosUi(TestPointOfSaleHttpCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.group_ids |= cls.env.ref('dallah_gym_core.group_gym_manager') | cls.env.ref('hr.group_hr_user')
        env = cls.env
        Branch = env['res.branch']
        cls.bbm = Branch.create({'name': "Izghawa Men's Gym", 'code': 'BBM'})
        cls.bbu = Branch.create({'name': "Mashaff Men's Gym", 'code': 'BBU'})
        cls.ladies = Branch.create({'name': 'Al Rayyan Ladies Gym', 'code': 'LAD'})
        cls.main_pos_config.write({
            'gym_branch_id': cls.bbm.id,
            'default_allowed_branch_ids': [Command.set((cls.bbm | cls.bbu).ids)],
            'use_dot_matrix_receipt': True,
        })
        cls.member = env['res.partner'].create({'name': 'Nasser Al-Kuwari', 'is_gym_member': True})
        cls.coach = env['hr.employee'].create({
            'name': 'Coach Alex Rodriguez', 'is_coach': True, 'allowed_branch_ids': [Command.set(cls.bbm.ids)],
        })
        common = {'available_in_pos': True, 'type': 'service', 'taxes_id': [Command.clear()]}
        cls.water = env['product.product'].create({'name': 'Bottled Water', 'list_price': 2.0, **common})
        cls.plan = env['product.product'].create({
            'name': '6 Months Full Gym', 'list_price': 2500.0, **common,
            'is_gym_membership': True, 'membership_type': 'gym',
            'membership_duration_val': 6, 'membership_duration_unit': 'months',
        })
        cls.pt = env['product.product'].create({
            'name': 'PT 26', 'list_price': 1800.0, **common,
            'is_gym_membership': True, 'membership_type': 'pt', 'pt_total_sessions': 26,
            'membership_duration_val': 1, 'membership_duration_unit': 'months',
        })

    def test_gym_checkout_tour(self):
        self.pos_user.write({
            'group_ids': [Command.link(self.env.ref('dallah_gym_core.group_gym_cashier').id)],
            'gym_branch_ids': [Command.set(self.bbm.ids)],
        })
        self.main_pos_config.with_user(self.pos_user).open_ui()
        self.start_pos_tour('DallahGymCheckoutTour', login='pos_user')
        order = self.env['pos.order'].search([('partner_id', '=', self.member.id)], limit=1)
        line_info = [(l.product_id.name, l.membership_start_date, l.membership_end_date, l.coach_id.name, l.pt_slot_hour)
                     for l in order.lines]
        self.assertEqual(order.allowed_branch_ids, self.bbm | self.bbu, line_info)
        pt_line = order.lines.filtered(lambda l: l.product_id == self.pt)
        self.assertEqual(pt_line.coach_id, self.coach, line_info)
        membership = self.env['gym.membership'].search([('partner_id', '=', self.member.id)])
        self.assertEqual(set(membership.product_id.ids), {self.plan.id, self.pt.id})
        pt_membership = membership.filtered(lambda m: m.product_id == self.pt)
        self.assertEqual(pt_membership.coach_id, self.coach)
        self.assertEqual(pt_membership.pt_slot_hour, 19.0)
        self.assertEqual(len(pt_membership.pt_session_ids), 26)
        self.assertEqual(self.member.allowed_branch_ids, self.bbm | self.bbu)
        self.assertEqual(self.member.membership_state, 'active')
