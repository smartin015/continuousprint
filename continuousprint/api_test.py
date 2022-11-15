import unittest
import json
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

    def test_role_access_denied(self):
        testcases = [
            ("STARTSTOP", "/set_active"),
            ("ADDSET", "/set/add"),
            ("ADDJOB", "/job/add"),
            ("ADDJOB", "/job/import"),
            ("EDITJOB", "/job/mv"),
            ("EDITJOB", "/job/edit"),
            ("EDITJOB", "/job/reset"),
            ("EXPORTJOB", "/job/export"),
            ("RMJOB", "/job/rm"),
            ("GETHISTORY", "/history/get"),
            ("CLEARHISTORY", "/history/reset"),
            ("GETQUEUES", "/queues/get"),
            ("EDITQUEUES", "/queues/edit"),
            ("GETAUTOMATION", "/automation/get"),
            ("EDITAUTOMATION", "/automation/edit"),
        ]

        num_handlers_tested = len(set([tc[1] for tc in testcases]))
        num_handlers = len(
            [
                f
                for f in dir(self.api)
                if hasattr(getattr(self.api, f), "_blueprint_rules")
            ]
        )
        self.assertEqual(
            num_handlers_tested, num_handlers - 1
        )  # /state/get is unrestricted

        num_perms_tested = len(set([tc[0] for tc in testcases]))
        num_perms = len([p for p in Permission])
        self.assertEqual(num_perms_tested, num_perms)

        for (role, endpoint) in testcases:
            p = getattr(self.perm, f"PLUGIN_CONTINUOUSPRINT_{role}")
            p.can.return_value = False
            if role.startswith("GET"):
                rep = self.client.get(endpoint)
            else:
                rep = self.client.post(endpoint)
            self.assertEqual(rep.status_code, 403)

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
        self.perm.PLUGIN_CONTINUOUSPRINT_ADDSET.can.return_value = True
        data = dict(foo="bar", job="jid")
        self.api._get_queue = MagicMock()
        self.api._get_queue().add_set.return_value = "ret"
        self.api._preprocess_set = lambda s: s
        rep = self.client.post("/set/add", data=dict(json=json.dumps(data)))
        self.assertEqual(rep.status_code, 200)
        self.api._get_queue().add_set.assert_called_with("jid", data)
        self.assertEqual(rep.get_data(as_text=True), '"ret"')

    def test_add_job(self):
        self.perm.PLUGIN_CONTINUOUSPRINT_ADDJOB.can.return_value = True
        data = dict(name="jobname")
        self.api._get_queue = MagicMock()
        self.api._get_queue().add_job().as_dict.return_value = "ret"
        rep = self.client.post("/job/add", data=dict(json=json.dumps(data)))
        self.assertEqual(rep.status_code, 200)
        self.api._get_queue().add_job.assert_called_with("jobname")
        self.assertEqual(rep.get_data(as_text=True), '"ret"')

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

    def test_edit_queues(self):
        self.skipTest("TODO")

    def test_edit_scripts(self):
        self.skipTest("TODO")

    def test_get_scripts(self):
        self.skipTest("TODO")
