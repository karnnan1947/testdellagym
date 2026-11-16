from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    is_coach = fields.Boolean(string='Is Coach', default=False, index=True)
    allowed_branch_ids = fields.Many2many(
        'res.branch', 'hr_employee_gym_branch_rel', 'employee_id', 'branch_id',
        string='Coach Branches')
    coach_shift_ids = fields.One2many('hr.employee.coach.shift', 'employee_id', string='Split Shifts')
    booking_horizon_days = fields.Integer(string='Booking Horizon (Days)', default=30)


class HrEmployeePublic(models.Model):
    """Expose coach data to users without HR rights (cashiers, POS)."""
    _inherit = 'hr.employee.public'

    is_coach = fields.Boolean(readonly=True)
    booking_horizon_days = fields.Integer(readonly=True)
    allowed_branch_ids = fields.Many2many('res.branch', related='employee_id.allowed_branch_ids')
    coach_shift_ids = fields.One2many('hr.employee.coach.shift', related='employee_id.coach_shift_ids')
