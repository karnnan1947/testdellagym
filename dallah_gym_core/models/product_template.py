from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    is_gym_membership = fields.Boolean(
        string='Is Gym Membership', default=False, index=True,
        help='Enables membership calculation & POS pre-payment check.')
    membership_type = fields.Selection(
        [('gym', 'Gym Access'), ('pt', 'Personal Training'), ('class', 'Class / Taekwondo')],
        string='Category')
    membership_duration_val = fields.Integer(string='Duration Value', default=1)
    membership_duration_unit = fields.Selection(
        [('days', 'Days'), ('weeks', 'Weeks'), ('months', 'Months'), ('years', 'Years')],
        string='Duration Unit', default='months')
    pt_total_sessions = fields.Integer(string='Total Sessions', default=0)
    reminder_days_before = fields.Integer(
        string='Reminder Lead (Days)', default=10,
        help='Days before expiry to trigger automated email notice.')
