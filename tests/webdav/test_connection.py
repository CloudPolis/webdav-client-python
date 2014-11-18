__author__ = 'designerror'

import allure
#from hamcrest import *

class TestRequiredOptions:

    def test_without_webdav_hostname(self):
        options = { 'webdav_server': "https://webdav.yandex.ru",
                    'webda_login': "designerror",
                    'webdav_password': "yxKeksiki_8"}
        allure.attach('options', options.__str__())
        assert 0
