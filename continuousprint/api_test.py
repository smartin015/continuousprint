import unittest
import json
import logging
from .driver import Action as DA
from .storage.database import DEFAULT_QUEUE
from unittest.mock import patch, MagicMock, call, PropertyMock
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
        self.api._get_queue = MagicMock()
        self.api._get_key = lambda k, d: d
        self.api._logger = logging.getLogger()
        self.app.register_blueprint(self.api.get_blueprint())
        self.app.config.update({"TESTING": True})
        self.client = self.app.test_client()

    def test_role_access_denied(self):
        testcases = [
            ("GETSTATE", "/state/get"),
            ("STARTSTOP", "/set_active"),
            ("ADDSET", "/set/add"),
            ("ADDJOB", "/job/add"),
            ("EDITJOB", "/job/mv"),
            ("EDITJOB", "/job/edit"),
            ("ADDJOB", "/job/import"),
            ("EXPORTJOB", "/job/export"),
            ("RMJOB", "/job/rm"),
            ("EDITJOB", "/job/reset"),
            ("GETHISTORY", "/history/get"),
            ("RESETHISTORY", "/history/reset"),
            ("GETQUEUES", "/queues/get"),
            ("EDITQUEUES", "/queues/edit"),
            ("GETAUTOMATION", "/automation/get"),
            ("EDITAUTOMATION", "/automation/edit"),
            ("EDITAUTOMATION", "/automation/external"),
            ("EDITAUTOMATION", "/automation/simulate"),
        ]
        self.api._get_queue = None  # MagicMock interferes with checking

        num_handlers_tested = len(set([tc[1] for tc in testcases]))
        handlers = [
            f
            for f in dir(self.api)
            if hasattr(getattr(self.api, f), "_blueprint_rules")
        ]
        self.assertEqual(num_handlers_tested, len(handlers))

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
        self.perm.PLUGIN_CONTINUOUSPRINT_GETSTATE.can.return_value = True
        self.api._state_json = lambda: "foo"
        rep = self.client.get("/state/get")
        self.assertEqual(rep.status_code, 200)
        self.assertEqual(rep.data, b"foo")

    def test_set_active(self):
        self.perm.PLUGIN_CONTINUOUSPRINT_STARTSTOP.can.return_value = True
        self.api._update = MagicMock()
        self.api._state_json = lambda: "foo"
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
        self.api._get_queue().add_set.return_value = "ret"
        self.api._preprocess_set = lambda s: s

        rep = self.client.post("/set/add", data=dict(json=json.dumps(data)))

        self.assertEqual(rep.status_code, 200)
        self.assertEqual(rep.get_data(as_text=True), '"ret"')
        self.api._get_queue().add_set.assert_called_with("jid", data)

    def test_add_job(self):
        self.perm.PLUGIN_CONTINUOUSPRINT_ADDJOB.can.return_value = True
        data = dict(name="jobname")
        self.api._get_queue().add_job().as_dict.return_value = "ret"

        rep = self.client.post("/job/add", data=dict(json=json.dumps(data)))

        self.assertEqual(rep.status_code, 200)
        self.assertEqual(rep.get_data(as_text=True), '"ret"')
        self.api._get_queue().add_job.assert_called_with("jobname")

    def test_mv_job_no_before_id(self):
        self.perm.PLUGIN_CONTINUOUSPRINT_EDITJOB.can.return_value = True
        data = dict(id="foo", after_id="bar", src_queue="q1", dest_queue="q2")

        rep = self.client.post("/job/mv", data=data)

        self.assertEqual(rep.status_code, 200)
        self.api._get_queue().mv_job.assert_called_with(
            data["id"], data["after_id"], None
        )

    def test_mv_job(self):
        self.perm.PLUGIN_CONTINUOUSPRINT_EDITJOB.can.return_value = True
        data = dict(
            id="foo", after_id="bar", before_id="baz", src_queue="q1", dest_queue="q2"
        )

        rep = self.client.post("/job/mv", data=data)

        self.assertEqual(rep.status_code, 200)
        self.api._get_queue().mv_job.assert_called_with(
            data["id"], data["after_id"], data["before_id"]
        )

    def test_edit_job(self):
        self.perm.PLUGIN_CONTINUOUSPRINT_EDITJOB.can.return_value = True
        data = dict(id="foo", queue="queue")
        self.api._get_queue().edit_job.return_value = "ret"
        rep = self.client.post("/job/edit", data=dict(json=json.dumps(data)))

        self.assertEqual(rep.status_code, 200)
        self.assertEqual(rep.get_data(as_text=True), '"ret"')
        self.api._get_queue().edit_job.assert_called_with(data["id"], data)

    def test_import_job(self):
        self.perm.PLUGIN_CONTINUOUSPRINT_ADDJOB.can.return_value = True
        data = dict(path="path", queue="queue")
        self.api._get_queue().import_job().as_dict.return_value = "ret"
        rep = self.client.post("/job/import", data=data)

        self.assertEqual(rep.status_code, 200)
        self.assertEqual(rep.get_data(as_text=True), '"ret"')
        self.api._get_queue().import_job.assert_called_with(data["path"])

    def test_export_job(self):
        self.perm.PLUGIN_CONTINUOUSPRINT_EXPORTJOB.can.return_value = True
        data = {"job_ids[]": ["1", "2", "3"]}
        self.api._get_queue().export_job.return_value = "ret"
        self.api._path_in_storage = lambda p: p
        self.api._path_on_disk = lambda p, sd: p
        rep = self.client.post("/job/export", data=data)

        self.assertEqual(rep.status_code, 200)
        self.assertEqual(
            json.loads(rep.get_data(as_text=True)),
            dict(errors=[], paths=["ret", "ret", "ret"]),
        )
        self.api._get_queue().export_job.assert_has_calls(
            [call(int(i), "/") for i in data["job_ids[]"]]
        )

    def test_rm_job(self):
        self.perm.PLUGIN_CONTINUOUSPRINT_RMJOB.can.return_value = True
        data = {"queue": "q", "job_ids[]": ["1", "2", "3"]}
        self.api._get_queue().remove_jobs.return_value = "ret"

        rep = self.client.post("/job/rm", data=data)

        self.assertEqual(rep.status_code, 200)
        self.assertEqual(rep.get_data(as_text=True), '"ret"')
        self.api._get_queue().remove_jobs.assert_called_with(data["job_ids[]"])

    def test_reset_multi(self):
        self.perm.PLUGIN_CONTINUOUSPRINT_EDITJOB.can.return_value = True
        data = {"queue": "q", "job_ids[]": ["1", "2", "3"]}
        self.api._get_queue().reset_jobs.return_value = "ret"

        rep = self.client.post("/job/reset", data=data)

        self.assertEqual(rep.status_code, 200)
        self.assertEqual(rep.get_data(as_text=True), '"ret"')
        self.api._get_queue().reset_jobs.assert_called_with(data["job_ids[]"])

    def test_get_history(self):
        self.perm.PLUGIN_CONTINUOUSPRINT_GETHISTORY.can.return_value = True
        self.api._history_json = lambda: "foo"
        rep = self.client.get("/history/get")
        self.assertEqual(rep.status_code, 200)
        self.assertEqual(rep.data, b"foo")

    @patch("continuousprint.api.queries")
    def test_reset_history(self, q):
        self.perm.PLUGIN_CONTINUOUSPRINT_RESETHISTORY.can.return_value = True
        rep = self.client.post("/history/reset")
        q.resetHistory.assert_called_once()
        self.assertEqual(rep.status_code, 200)
        self.assertEqual(rep.data, b'"OK"')

    @patch("continuousprint.api.queries")
    def test_get_queues(self, q):
        self.perm.PLUGIN_CONTINUOUSPRINT_GETQUEUES.can.return_value = True
        self.api._get_key = lambda k, d: True

        self.api._peerprint = MagicMock()
        self.api._peerprint.get_plugin().client.get_connections.return_value = [
            MagicMock(network="foo", addr="1234"),
            MagicMock(network="bar", addr="1234"),
        ]

        mq = MagicMock(rank=0)
        mq.name = "foo"
        mq.as_dict.return_value = dict(name="foo")
        lq = MagicMock(rank=1)
        lq.name = DEFAULT_QUEUE
        lq.as_dict.return_value = dict(name=DEFAULT_QUEUE)
        q.getQueues.return_value = [mq, lq]

        rep = self.client.get("/queues/get")
        self.assertEqual(rep.status_code, 200)
        self.assertEqual(
            json.loads(rep.get_data(as_text=True)),
            [
                dict(name=DEFAULT_QUEUE, enabled=True, rank=1),
                dict(name="foo", enabled=True, addr="1234", strategy="LINEAR"),
                dict(name="bar", enabled=False, addr="1234", strategy="LINEAR"),
            ],
        )

    @patch("continuousprint.api.queries")
    def test_edit_queues(self, q):
        self.perm.PLUGIN_CONTINUOUSPRINT_EDITQUEUES.can.return_value = True
        q.assignQueues.return_value = ("absent", "added")
        self.api._commit_queues = MagicMock()
        rep = self.client.post(
            "/queues/edit",
            data=dict(
                json=json.dumps(
                    [dict(name="foo", enabled=True), dict(name="bar", enabled=False)]
                )
            ),
        )
        q.assignQueues.assert_called_with([dict(name="foo", enabled=True)])
        self.assertEqual(rep.status_code, 200)
        self.assertEqual(rep.data, b'"OK"')
        self.api._commit_queues.assert_called_with("added", "absent")

    @patch("continuousprint.api.queries")
    def test_edit_automation(self, q):
        self.perm.PLUGIN_CONTINUOUSPRINT_EDITAUTOMATION.can.return_value = True
        rep = self.client.post(
            "/automation/edit",
            data=dict(
                json=json.dumps(
                    dict(
                        scripts="scripts",
                        events="events",
                        preprocessors="preprocessors",
                    )
                )
            ),
        )
        self.assertEqual(rep.status_code, 200)
        self.assertEqual(rep.data, b'"OK"')
        q.assignAutomation.assert_called_with("scripts", "preprocessors", "events")

    @patch("continuousprint.api.queries")
    def test_get_automation(self, q):
        self.perm.PLUGIN_CONTINUOUSPRINT_GETAUTOMATION.can.return_value = True
        q.getAutomation.return_value = "foo"
        rep = self.client.get("/automation/get")
        self.assertEqual(rep.status_code, 200)
        self.assertEqual(rep.data, b'"foo"')

    @patch("continuousprint.api.queries")
    def test_automation_external(self, q):
        self.perm.PLUGIN_CONTINUOUSPRINT_EDITAUTOMATION.can.return_value = True
        self.api._set_external_symbols = MagicMock()
        rep = self.client.post("/automation/external", json=dict(foo="bar"))
        self.assertEqual(rep.status_code, 200)
        self.api._set_external_symbols.assert_called_with(dict(foo="bar"))

    @patch("continuousprint.api.getInterpreter")
    @patch("continuousprint.api.genEventScript")
    def test_automation_simulate(self, ge, gi):
        self.perm.PLUGIN_CONTINUOUSPRINT_EDITAUTOMATION.can.return_value = True
        st = PropertyMock(side_effect=[dict(), dict(b=2, c=3)])
        mi = MagicMock()
        type(mi).symtable = st
        out = MagicMock()
        out.read.return_value = "stdout"
        err = MagicMock()
        err.read.return_value = "stderr"

        gi.return_value = (mi, out, err)
        ge.return_value = "gcode"

        rep = self.client.post(
            "/automation/simulate",
            data=dict(
                automation=json.dumps([]),
                symtable=json.dumps(dict(a=1, b=1)),
            ),
        )
        self.assertEqual(rep.status_code, 200)
        self.assertEqual(
            json.loads(rep.get_data(as_text=True)),
            {
                "gcode": "gcode",
                "stderr": "stderr",
                "stdout": "stdout",
                "symtable_diff": {"b": "2", "c": "3"},
            },
        )
