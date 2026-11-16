from odoo import fields, models


class ResBranch(models.Model):
    _inherit = 'res.branch'

    zkbio_access_group_id = fields.Char(
        string='ZKBio Door Access Group ID',
        help='ZKBio CVSecurity door access group granting this branch turnstiles (e.g. GRP_IZGHAWA_MEN).')
    zkbio_device_ids = fields.Char(
        string='Turnstile Devices',
        help='Comma-separated ZKBio device names / serials of this branch (e.g. ProFace-BBM-01, ProFace-BBM-02). '
             'Used to map imported gate scans to the branch.')

    def _zkbio_device_list(self):
        self.ensure_one()
        return [d.strip().lower() for d in (self.zkbio_device_ids or '').split(',') if d.strip()]


class ResPartner(models.Model):
    _inherit = 'res.partner'

    zkbio_card_number = fields.Char(string='Badge / Card Number', copy=False,
                                    help='Physical badge bound in ZKBio. Falls back to the QID when empty.')
    zkbio_queue_ids = fields.One2many('zkbio.sync.queue', 'partner_id', string='ZKBio Sync Queue')
