from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install')
class TestZkbioUi(HttpCase):

    def test_settings_page_loads(self):
        self.browser_js(
            '/odoo/settings#dallah_gym_zkbio',
            "console.log('test successful')",
            ready="document.body.textContent.includes('Branch Gate Door Mapping') && document.body.textContent.includes('Test Connection')",
            login='admin')
