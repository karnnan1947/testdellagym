from datetime import date

from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install')
class TestGymUi(HttpCase):

    def test_pt_reception_board_loads(self):
        branch = self.env['res.branch'].create({'name': "Izghawa Men's Gym", 'code': 'BBM'})
        coach = self.env['hr.employee'].create({
            'name': 'Coach Alex Rodriguez', 'is_coach': True, 'allowed_branch_ids': [(6, 0, branch.ids)]})
        member = self.env['res.partner'].create({'name': 'Nasser Al-Kuwari', 'is_gym_member': True})
        self.env['gym.pt.session'].create({
            'partner_id': member.id, 'coach_id': coach.id, 'branch_id': branch.id,
            'session_date': date.today(), 'start_hour': 10.0, 'end_hour': 11.0})
        self.browser_js(
            '/odoo/action-dallah_gym_core.action_gym_pt_reception_board',
            "console.log('test successful')",
            ready="document.querySelector('.o_gym_pt_board .o_gym_grid')?.textContent.includes('Coach Alex Rodriguez')",
            login='admin')

    def test_member_and_settings_forms_load(self):
        member = self.env['res.partner'].create({'name': 'Nasser Al-Kuwari', 'is_gym_member': True})
        self.browser_js(
            f'/odoo/contacts/{member.id}',
            "console.log('test successful')",
            ready="!!document.querySelector('.o_form_view .o_notebook') && document.body.textContent.includes('Gym Membership')",
            login='admin')
