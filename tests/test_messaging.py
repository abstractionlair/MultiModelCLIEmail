import unittest
from unittest.mock import patch
import tempfile
import shutil
import importlib.util
import importlib.machinery
from pathlib import Path
from argparse import Namespace
from email.message import EmailMessage
import email.utils


_scripts_dir = Path(__file__).resolve().parent.parent / "scripts"
_spec = importlib.util.spec_from_file_location(
    "msgcli",
    _scripts_dir / "msg",
    loader=importlib.machinery.SourceFileLoader(
        "msgcli", str(_scripts_dir / "msg")
    ),
)
_msg_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_msg_module)


class TestMessagingCmdRead(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.mailbox = Path(self.temp_dir) / "mailbox"
        (self.mailbox / "new").mkdir(parents=True)
        (self.mailbox / "cur").mkdir(parents=True)
        (self.mailbox / "tmp").mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def _write_test_message(self, message_id, filename):
        msg = EmailMessage()
        msg["Message-ID"] = message_id
        msg["From"] = "sender@multimodel.local"
        msg["To"] = "recipient@multimodel.local"
        msg["Subject"] = "Test"
        msg["Date"] = email.utils.formatdate(localtime=True)
        msg.set_content("test body")
        with open(self.mailbox / "new" / filename, "w") as f:
            f.write(msg.as_string())

    def test_read_by_filename_still_works(self):
        """Filename partial match still finds the message."""
        self._write_test_message(
            "<msg-unrelated@multimodel.local>",
            "1690000000.testmatch.multimodel",
        )
        with patch.object(_msg_module, "get_role_mailbox", return_value=self.mailbox):
            args = Namespace(role="test", message_id="testmatch", headers=False)
            _msg_module.cmd_read(args)

    def test_read_by_message_id_header(self):
        """Finds message by Message-ID header when filename doesn't match."""
        msg_id = "<msg-test-abc123@multimodel.local>"
        self._write_test_message(msg_id, "1690000000.zzzzzzzz.multimodel")
        with patch.object(_msg_module, "get_role_mailbox", return_value=self.mailbox):
            args = Namespace(role="test", message_id=msg_id, headers=False)
            _msg_module.cmd_read(args)

    def test_partial_message_id_does_not_match_header(self):
        """Substrings of a Message-ID header must NOT match (exact only).

        A short or partial ID silently reading an unrelated message is
        worse than a not-found error.
        """
        msg_id = "<msg-test-substring@multimodel.local>"
        self._write_test_message(msg_id, "1690000000.zzzzzzzz.multimodel")
        with patch.object(_msg_module, "get_role_mailbox", return_value=self.mailbox):
            args = Namespace(role="test", message_id="msg-test-substring", headers=False)
            with self.assertRaises(SystemExit):
                _msg_module.cmd_read(args)

    def test_filename_match_is_deterministic_sorted_order(self):
        """When several filenames match, the lexicographically first wins."""
        self._write_test_message(
            "<msg-first@multimodel.local>", "1690000000.aaa.multimodel"
        )
        self._write_test_message(
            "<msg-second@multimodel.local>", "1690000001.bbb.multimodel"
        )
        with patch.object(_msg_module, "get_role_mailbox", return_value=self.mailbox):
            args = Namespace(role="test", message_id="multimodel", headers=False)
            _msg_module.cmd_read(args)
        # cmd_read marks the displayed message read (new/ -> cur/), so the
        # sorted-first file is the one that moved.
        self.assertFalse((self.mailbox / "new" / "1690000000.aaa.multimodel").exists())
        self.assertTrue((self.mailbox / "new" / "1690000001.bbb.multimodel").exists())

    def test_read_by_message_id_without_brackets(self):
        """Finds by Message-ID passed without angle brackets."""
        msg_id = "<msg-test-nobrackets@multimodel.local>"
        self._write_test_message(msg_id, "1690000000.yyyyyyyy.multimodel")
        with patch.object(_msg_module, "get_role_mailbox", return_value=self.mailbox):
            args = Namespace(role="test", message_id="msg-test-nobrackets@multimodel.local", headers=False)
            _msg_module.cmd_read(args)

    def test_read_from_cur_directory(self):
        """Finds message by Message-ID in cur/ directory."""
        msg_id = "<msg-cur-test@multimodel.local>"
        msg = EmailMessage()
        msg["Message-ID"] = msg_id
        msg["From"] = "sender@multimodel.local"
        msg["To"] = "recipient@multimodel.local"
        msg["Subject"] = "Cur Test"
        msg["Date"] = email.utils.formatdate(localtime=True)
        msg.set_content("cur body")
        with open(self.mailbox / "cur" / "1690000000.curmsg.multimodel", "w") as f:
            f.write(msg.as_string())
        with patch.object(_msg_module, "get_role_mailbox", return_value=self.mailbox):
            args = Namespace(role="test", message_id=msg_id, headers=False)
            _msg_module.cmd_read(args)

    def test_message_not_found(self):
        """cmd_read exits with error when neither filename nor header matches."""
        self._write_test_message(
            "<msg-known@multimodel.local>",
            "1690000000.knownone.multimodel",
        )
        with patch.object(_msg_module, "get_role_mailbox", return_value=self.mailbox):
            args = Namespace(role="test", message_id="nonexistent", headers=False)
            with self.assertRaises(SystemExit):
                _msg_module.cmd_read(args)
