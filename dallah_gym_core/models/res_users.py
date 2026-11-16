from odoo import fields, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    gym_branch_ids = fields.Many2many(
        'res.branch', 'res_users_gym_branch_rel', 'user_id', 'branch_id',
        string='Allowed Gym Branches',
        help='Counter users (cashier / receptionist) only see gym records of these branches.')
