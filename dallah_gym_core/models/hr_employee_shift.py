from odoo import api, fields, models
from odoo.exceptions import ValidationError

DAYS_OF_WEEK = [
    ('0', 'Monday'), ('1', 'Tuesday'), ('2', 'Wednesday'), ('3', 'Thursday'),
    ('4', 'Friday'), ('5', 'Saturday'), ('6', 'Sunday'),
]


class HrEmployeeCoachShift(models.Model):
    _name = 'hr.employee.coach.shift'
    _description = 'Coach Split Shift'
    _order = 'employee_id, day_of_week, start_hour'

    employee_id = fields.Many2one('hr.employee', string='Coach', required=True, ondelete='cascade', index=True)
    day_of_week = fields.Selection(DAYS_OF_WEEK, string='Day of Week', required=True)
    shift_type = fields.Selection(
        [('morning', 'Morning'), ('evening', 'Evening'), ('full', 'Full Day')],
        string='Shift', required=True, default='morning')
    branch_id = fields.Many2one('res.branch', string='Branch', required=True)
    start_hour = fields.Float(string='Start Hour', required=True)
    end_hour = fields.Float(string='End Hour', required=True)

    @api.constrains('start_hour', 'end_hour')
    def _check_hours(self):
        for shift in self:
            if not (0 <= shift.start_hour < shift.end_hour <= 24):
                raise ValidationError(self.env._("Shift hours must be within 0-24 and start before end."))
