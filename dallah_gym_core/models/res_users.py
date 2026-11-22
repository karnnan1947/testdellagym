from odoo import api, fields, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    gym_branch_ids = fields.Many2many(
        'res.branch', 'res_users_gym_branch_rel', 'user_id', 'branch_id',
        string='Allowed Gym Branches',
        help='Counter users (cashier / receptionist) only see gym records of these branches.')

    gym_access_branch_ids = fields.Many2many(
        'res.branch', compute='_compute_gym_access_branch_ids',
        help='Branches whose records the user may see: all of them for managers and for users '
             'outside the gym cashier/receptionist groups, otherwise only "Allowed Gym Branches". '
             'Used by the branch access rules on sales and POS orders.')

    @api.depends('gym_branch_ids', 'group_ids')
    def _compute_gym_access_branch_ids(self):
        all_branches = None
        manager = self.env.ref('dallah_gym_core.group_gym_manager')
        cashier = self.env.ref('dallah_gym_core.group_gym_cashier')
        for user in self:
            restricted = cashier in user.all_group_ids and manager not in user.all_group_ids
            if restricted:
                user.gym_access_branch_ids = user.gym_branch_ids
            else:
                if all_branches is None:
                    all_branches = self.env['res.branch'].sudo().with_context(active_test=False).search([])
                user.gym_access_branch_ids = all_branches
