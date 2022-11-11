import unittest
from .driver import Action as DA
from unittest.mock import patch, MagicMock
import imp
from flask import Flask
from .api import Permission, cpq_permission
import continuousprint.api


class TestPermission(unittest.TestCase):
    def test_as_dict(self):
        d = Permission.ADDJOB.as_dict()
        self.assertEqual(d["key"], "ADDJOB")

    @patch("continuousprint.api.Permissions")
    def test_wrap_permission_ok(self, perms):
        func = MagicMock(__name__="func")
        wrapped = cpq_permission(Permission.ADDSET)(func)

        perms.PLUGIN_CONTINUOUSPRINT_ADDSET.can.return_value = True
        wrapped()
        func.assert_called_once()

    @patch("continuousprint.api.flask")
    @patch("continuousprint.api.Permissions")
    def test_wrap_permission_err(self, perms, flask):
        func = MagicMock(__name__="func")
        flask.make_response.return_value = "retval"

        wrapped = cpq_permission(Permission.ADDSET)(func)
        perms.PLUGIN_CONTINUOUSPRINT_ADDSET.can.return_value = False
        got = wrapped()
        self.assertEqual(got, "retval")
        func.assert_not_called()


class TestAPI(unittest.TestCase):
    def setUp(self):  # , plugin, restrict):
        # Because handlers are decorated @restricted_access which
        # expects octoprint to be initialized, we have to patch the
        # decorator and reload the module so it isn't dependent on
        # octoprint internal state.
        def kill_patches():
            patch.stopall()
            imp.reload(continuousprint.api)

        self.addCleanup(kill_patches)
        patch(
            "continuousprint.api.octoprint.server.util.flask.restricted_access",
            lambda x: x,
        ).start()

        imp.reload(continuousprint.api)
        self.perm = patch("continuousprint.api.Permissions").start()
        patch.object(
            continuousprint.api.ContinuousPrintAPI, "__abstractmethods__", set()
        ).start()

        self.app = Flask(__name__)
        self.api = continuousprint.api.ContinuousPrintAPI()
        self.api._basefolder = "notexisty"
        self.api._identifier = "continuousprint"
        self.app.register_blueprint(self.api.get_blueprint())
        self.app.config.update({"TESTING": True})
        self.client = self.app.test_client()
        self.api._state_json = lambda: "foo"

    def test_get_state(self):
        rep = self.client.get("/state/get")
        self.assertEqual(rep.status_code, 200)
        self.assertEqual(rep.data, b"foo")

    def test_set_active(self):
        self.perm.PLUGIN_CONTINUOUSPRINT_STARTSTOP.can.return_value = True
        self.api._update = MagicMock()
        rep = self.client.post("/set_active", data=dict(active="true"))
        self.assertEqual(rep.status_code, 200)
        self.api._update.assert_called_with(DA.ACTIVATE)

        self.api._update.reset_mock()
        rep = self.client.post("/set_active", data=dict(active=True))
        self.assertEqual(rep.status_code, 200)
        self.api._update.assert_called_with(DA.ACTIVATE)

        self.api._update.reset_mock()
        rep = self.client.post("/set_active", data=dict(active=False))
        self.assertEqual(rep.status_code, 200)
        self.api._update.assert_called_with(DA.DEACTIVATE)

        self.api._update.reset_mock()
        rep = self.client.post("/set_active", data=dict(active="whatever"))
        self.assertEqual(rep.status_code, 200)
        self.api._update.assert_called_with(DA.DEACTIVATE)

    def test_add_set(self):
        self.skipTest("TODO")

    def test_add_job(self):
        self.skipTest("TODO")

    def test_mv_job(self):
        self.skipTest("TODO")

    def test_edit_job(self):
        self.skipTest("TODO")

    def test_import_job(self):
        self.skipTest("TODO")

    def test_export_job(self):
        self.skipTest("TODO")

    def test_rm_job(self):
        self.skipTest("TODO")

    def test_reset_multi(self):
        self.skipTest("TODO")

    def test_get_history(self):
        self.skipTest("TODO")

    def test_reset_history(self):
        self.skipTest("TODO")

    def test_get_queues(self):
        self.skipTest("TODO")

    def edit_queues(self):
        self.skipTest("TODO")
