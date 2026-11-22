from odoo import fields, models


class ResBranch(models.Model):
    """Physical gym branch / location (e.g. Izghawa Men's Gym (BBM)).

    Not a res.company: branches share one company and are used for turnstile
    access, coach assignment, POS counters and invoice analytics.
    """
    _name = 'res.branch'
    _description = 'Gym Branch'
    _order = 'sequence, name'

    name = fields.Char(string='Branch Name', required=True, translate=True)
    code = fields.Char(string='Code', help='Short branch code, e.g. BBM, BBU, UHD.')
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company', string='Company', required=True,
        default=lambda self: self.env.company)
    analytic_account_id = fields.Many2one(
        'account.analytic.account', string='Analytic Account',
        help='Analytic account set on invoice lines of sales made at this branch.')
    warehouse_id = fields.Many2one(
        'stock.warehouse', string='Warehouse', check_company=True,
        help='Stock of this branch. POS shops of the branch must use an operation type of this warehouse.')
    default_allowed_branch_ids = fields.Many2many(
        'res.branch', 'res_branch_default_access_rel', 'branch_id', 'allowed_branch_id',
        string='Default Turnstile Access Policy',
        help='Branches auto-filled as permitted turnstile branches on sales made from this branch.')

    _code_company_uniq = models.Constraint(
        'unique(code, company_id)', 'The branch code must be unique per company.')

    def _compute_display_name(self):
        for branch in self:
            branch.display_name = f"{branch.name} ({branch.code})" if branch.code else branch.name
